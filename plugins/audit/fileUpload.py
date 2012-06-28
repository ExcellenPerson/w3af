'''
fileUpload.py

Copyright 2006 Andres Riancho

This file is part of w3af, w3af.sourceforge.net .

w3af is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 2 of the License.

w3af is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with w3af; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

'''

import os.path
import tempfile

from itertools import repeat, izip

import core.controllers.outputManager as om
import core.data.kb.knowledgeBase as kb
import core.data.constants.severity as severity
import core.data.kb.vuln as vuln

from core.controllers.basePlugin.baseAuditPlugin import baseAuditPlugin
from core.controllers.w3afException import w3afException
from core.controllers.misc.temp_dir import get_temp_dir
from core.controllers.coreHelpers.fingerprint_404 import is_404

from core.data.options.option import option
from core.data.options.optionList import optionList
from core.data.fuzzer.fuzzer import createMutants, createRandAlNum


class fileUpload(baseAuditPlugin):
    '''
    Uploads a file and then searches for the file inside all known directories.
    
    @author: Andres Riancho ( andres.riancho@gmail.com )
    '''
    
    TEMPLATE_DIR = os.path.join('plugins', 'audit', 'fileUpload')
    

    def __init__(self):
        baseAuditPlugin.__init__(self)
        
        # User configured
        self._extensions = ['gif', 'html', 'bmp', 'jpg', 'png', 'txt']

    def audit(self, freq ):
        '''
        Searches for file upload vulns.
        
        @param freq: A fuzzableRequest
        '''
        if freq.getMethod().upper() == 'POST' and len ( freq.getFileVariables() ) != 0:
            om.out.debug( 'fileUpload plugin is testing: ' + freq.getURL() )
            
            for file_parameter in freq.getFileVariables():
                fileh_filen_list = self._create_files()
                # Only file handlers are passed to the createMutants functions
                file_handlers = [ i[0] for i in fileh_filen_list ]
                mutants = createMutants( freq, file_handlers, fuzzableParamList=[file_parameter, ] )

                for mutant in mutants:
                    _, filename = os.path.split( mutant.getModValue().name )
                    mutant.uploaded_file_name = filename
       
                self._send_mutants_in_threads(self._uri_opener.send_mutant,
                                              mutants,
                                              self._analyze_result)
            
            self._remove_files(fileh_filen_list)
            
    def _create_files( self ):
        '''
        If the extension is in the templates dir, open it and return the handler.
        If the extension isn't in the templates dir, create a file with random 
        content, open it and return the handler.
        
        @return: A list of tuples with (file handler, file name)
        '''
        result = []
        
        for ext in self._extensions:
            # Open target
            temp_dir = get_temp_dir()
            low_level_fd, file_name = tempfile.mkstemp(prefix='w3af_', 
                                                       suffix='.' + ext,
                                                       dir=temp_dir)
            file_handler = os.fdopen(low_level_fd, "w+b")

            template_filename = 'template.' + ext
            if template_filename in os.listdir( self.TEMPLATE_DIR ):
                content = file( os.path.join(self.TEMPLATE_DIR, template_filename)).read()
            else:
                # Since I don't have a template for this file extension, I'll simply
                # put some random alnum inside the file
                content = createRandAlNum(64)
                
            # Write content to target
            file_handler.write(content)
            file_handler.close()
            
            # Open the target again, should never fail.
            try:
                file_handler = file( file_name, 'r')
            except:
                raise w3afException('Failed to open temp file: "%s".' % file_name)
            else:
                _, file_name = os.path.split(file_name)
                result.append( (file_handler, file_name) )
        
        return result
    
    def _remove_files(self, fileh_filen_list):
        '''
        Close all open files and remove them from disk. This is the reverse of 
        _create_files method.
        
        @param fileh_filen_list: A list of tuples as generated by _create_files
        @return: None
        
        >>> from core.controllers.misc.temp_dir import create_temp_dir
        >>> _ = create_temp_dir()
        >>> fu = fileUpload()
        >>> dir_before = os.listdir( get_temp_dir() )
        >>> fileh_filen_list = fu._create_files()
        >>> fu._remove_files(fileh_filen_list)
        >>> dir_after = os.listdir( get_temp_dir() )
        >>> dir_before == dir_after
        True
        
        '''
        for tmp_file_handle, tmp_file_name in fileh_filen_list:
            try:
                tmp_file_handle.close()
                fname = os.path.join( get_temp_dir() , tmp_file_name )
                os.remove(fname)
            except:
                pass        
    
    def _analyze_result(self, mutant, mutant_response):
        '''
        Analyze results of the _send_mutant method. 
        
        In this case, check if the file was uploaded to any of the known
        directories, or one of the "default" ones like "upload" or "files".
        '''
        if self._has_no_bug(mutant):        
            
            # Gen expr for directories where I can search for the uploaded file
            domain_path_list = set(u.getDomainPath() for u in 
                                   kb.kb.getData('urls' , 'url_objects'))
            
            # FIXME: Note that in all cases where I'm using kb's url_object info
            # I'll be making a mistake if the audit plugin is run before all
            # discovery plugins haven't run yet, since I'm not letting them
            # find all directories; which will make the current plugin run with
            # less information.

            url_generator = self._generate_urls(domain_path_list, mutant.uploaded_file_name)
            mutant_repeater = repeat( mutant )
            http_response_repeater = repeat( mutant_response )
            args = izip(url_generator, mutant_repeater, http_response_repeater)
            
            self._tm.threadpool.map_multi_args(self._confirm_file_upload,
                                               args)
    
    def _confirm_file_upload(self, path, mutant, http_response):
        '''
        Confirms if the file was uploaded to path
        
        @param path: The URL where we suspect that a file was uploaded to.
        @param mutant: The mutant that originated the file on the remote end
        @param http_response: The HTTP response asociated with sending mutant
        '''
        get_response = self._uri_opener.GET(path, cache=False)
        
        if not is_404(get_response) and self._has_no_bug(mutant):
            # This is necessary, if I don't do this, the session
            # saver will break cause REAL file objects can't 
            # be picked
            mutant.setModValue('<file_object>')
            v = vuln.vuln(mutant)
            v.setPluginName(self.getName())
            v.setId([http_response.id, get_response.id])
            v.setSeverity(severity.HIGH)
            v.setName('Insecure file upload')
            v['fileDest'] = get_response.getURL()
            v['fileVars'] = mutant.getFileVariables()
            msg = ('A file upload to a directory inside the '
            'webroot was found at: ' + mutant.foundAt())
            v.setDesc(msg)
            kb.kb.append(self, 'fileUpload', v)
            return
    
    def end(self):
        '''
        This method is called when the plugin wont be used anymore.
        '''
        self.print_uniq( kb.kb.getData( 'fileUpload', 'fileUpload' ), 'VAR' )        
        
    def _generate_urls( self, domain_path_list, uploaded_file_name ):
        '''
        @parameter url: A URL where the uploaded_file_name could be
        @parameter uploaded_file_name: The name of the file that was uploaded to the server
        @return: A list of paths where the file could be.
        '''
        tmp = ['uploads', 'upload', 'file', 'user', 'files', 'downloads', 
               'download', 'up', 'down']
        
        for url in domain_path_list:
            for default_path in tmp:
                for sub_url in url.getDirectories():
                    possible_location = sub_url.urlJoin( default_path + '/' )
                    possible_location = possible_location.urlJoin( uploaded_file_name )
                    yield possible_location
        
    def getOptions( self ):
        '''
        @return: A list of option objects for this plugin.
        '''
        ol = optionList()
        
        d = 'Extensions that w3af will try to upload through the form.'
        h = 'When finding a form with a file upload, this plugin will try to'
        h += '  upload a set of files with the extensions specified here.'
        o = option('extensions', self._extensions, d, 'list', help=h)

        ol.add(o)
        
        return ol
        
    def setOptions( self, optionsMap ):
        '''
        This method sets all the options that are configured using the user interface 
        generated by the framework using the result of getOptions().
        
        @parameter OptionList: A dictionary with the options for the plugin.
        @return: No value is returned.
        ''' 
        self._extensions = optionsMap['extensions'].getValue()
    
    def getLongDesc( self ):
        '''
        @return: A DETAILED description of the plugin functions and features.
        '''
        return '''
        This plugin will try to expoit insecure file upload forms.
        
        One configurable parameter exists:
            - extensions
        
        The extensions parameter is a comma separated list of extensions that 
        this plugin will try to upload. Many web applications verify the extension
        of the file being uploaded, if special extensions are required, they can
        be added here.
    
        Some web applications check the contents of the files being uploaded to
        see if they are really what their extension is telling. To bypass this
        check, this plugin uses file templates located at "plugins/audit/fileUpload/",
        this templates are valid files for each extension that have a section
        (the comment field in a gif file for example ) that can be replaced
        by scripting code ( PHP, ASP, etc ).
        
        After uploading the file, this plugin will try to find it on common
        directories like "upload" and "files" on every know directory. If the
        file is found, a vulnerability exists. 
        '''
