'''
test_scalable_bloom.py

Copyright 2012 Andres Riancho

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
import random
import unittest
import string

from nose.plugins.attrib import attr

from core.data.bloomfilter.scalable_bloom import ScalableBloomFilter


class TestScalableBloomfilter(unittest.TestCase):

    @attr('smoke')
    def test_bloom_int(self):

        f = ScalableBloomFilter(mode=ScalableBloomFilter.SMALL_SET_GROWTH)

        for i in xrange(0, 10000):
            _ = f.add(i)
        
        self.assertEqual( len(f), 10000)
        
        for i in xrange(0, 10000):
            self.assertEqual(i in f, True)

        for i in xrange(0, 10000 / 2 ):
            r = random.randint(0,10000-1)
            self.assertEqual(r in f, True)

        for i in xrange(0, 10000 / 2 ):
            r = random.randint(10000,10000 * 2)
            self.assertEqual(r in f, False)

    @attr('smoke')
    def test_bloom_string(self):
        f = ScalableBloomFilter(mode=ScalableBloomFilter.SMALL_SET_GROWTH)

        for i in xrange(0, 10000):
            rnd = ''.join(random.choice(string.letters) for i in xrange(40))
            _ = f.add(rnd)

        self.assertEqual(rnd in f, True)

        for i in string.letters:
            self.assertEqual(i in f, False)

        self.assertEqual(rnd in f, True)

