#!/usr/bin/python

# Converts .xlf files into .json files for use at http://translatewiki.net.
#
# Copyright 2013 Google Inc.
# https://developers.google.com/blockly/
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os
import re
import subprocess
import sys
from xml.dom import minidom
from common import InputError
from common import write_files

# Global variables
args = None  # Parsed command-line arguments.


def _parse_trans_unit(trans_unit):
    """Converts a trans-unit XML node into a more convenient dictionary format.

    Args:
        trans_unit: An XML representation of a .xlf translation unit.

    Returns:
        A dictionary with useful information about the translation unit.
        The returned dictionary is guaranteed to have an entry for 'key' and
        may have entries for 'source', 'target', 'description', and 'meaning'
        if present in the argument.

    Raises:
        InputError: A required field was not present.
    """

    def get_value(tag_name):
        elts = trans_unit.getElementsByTagName(tag_name)
        if not elts:
            return None
        elif len(elts) == 1:
            return ''.join([child.toxml() for child in elts[0].childNodes])
        else:
            raise InputError('', 'Unable to extract ' + tag_name)

    result = {}
    key = trans_unit.getAttribute('id')
    if not key:
        raise InputError('', 'id attribute not found')
    result['key'] = key

    # Get source and target, if present.
    try:
        result['source'] = get_value('source')
        result['target'] = get_value('target')
    except InputError, e:
        raise InputError(key, e.msg)

    # Get notes, using the from value as key and the data as value.
    notes = trans_unit.getElementsByTagName('note')
    for note in notes:
        from_value = note.getAttribute('from')
        if from_value and len(note.childNodes) == 1:
            result[from_value] = note.childNodes[0].data
        else:
            raise InputError(key, 'Unable to extract ' + from_value)

    return result


def _process_file(filename):
    """Builds list of translation units from input file.

    Each translation unit in the input file includes:
    - an id (opaquely generated by Soy)
    - the Blockly name for the message
    - the text in the source language (generally English)
    - a description for the translator

    The Soy and Blockly ids are joined with a hyphen and serve as the
    keys in both output files.  The value is the corresponding text (in the
    <lang>.json file) or the description (in the qqq.json file).

    Args:
        filename: The name of an .xlf file produced by Closure.

    Raises:
        IOError: An I/O error occurred with an input or output file.
        InputError: The input file could not be parsed or lacked required
            fields.

    Returns:
        A list of dictionaries produced by parse_trans_unit().
    """
    try:
        results = []  # list of dictionaries (return value)
        names = []    # list of names of encountered keys (local variable)
        try:
            parsed_xml = minidom.parse(filename)
        except IOError:
            # Don't get caught by below handler
            raise
        except Exception, e:
            print
            raise InputError(filename, str(e))

        # Make sure needed fields are present and non-empty.
        for trans_unit in parsed_xml.getElementsByTagName('trans-unit'):
            unit = _parse_trans_unit(trans_unit)
            for key in ['description', 'meaning', 'source']:
                if not key in unit or not unit[key]:
                    raise InputError(filename + ':' + unit['key'],
                                     key + ' not found')
            if unit['description'].lower() == 'ibid':
              if unit['meaning'] not in names:
                # If the term has not already been described, the use of 'ibid'
                # is an error.
                raise InputError(
                    filename,
                    'First encountered definition of: ' + unit['meaning']
                    + ' has definition: ' + unit['description']
                    + '.  This error can occur if the definition was not'
                    + ' provided on the first appearance of the message'
                    + ' or if the source (English-language) messages differ.')
              else:
                # If term has already been 
                # described, 'ibid' was used correctly,
                # and we output nothing.
                pass
            else:
              if unit['meaning'] in names:
                raise InputError(filename,
                                 'Second definition of: ' + unit['meaning'])
              names.append(unit['meaning'])
              results.append(unit)

        return results
    except IOError, e:
        print 'Error with file {0}: {1}'.format(filename, e.strerror)
        sys.exit(1)


def sort_units(units, templates):
    """Sorts the translation units by their definition order in the template.

    Args:
        units: A list of dictionaries produced by parse_trans_unit()
            that have a non-empty value for the key 'meaning'.
        templates: A string containing the Soy templates in which each of
            the units' meanings is defined.

    Returns:
        A new list of translation units, sorted by the order in which
        their meaning is defined in the templates.

    Raises:
        InputError: If a meaning definition cannot be found in the
            templates.
    """
    def key_function(unit):
        match = re.search(
            '\\smeaning\\s*=\\s*"{0}"\\s'.format(unit['meaning']),
            templates)
        if match:
            return match.start()
        else:
            raise InputError(args.templates,
                             'msg definition for meaning not found: ' +
                             unit['meaning'])
    return sorted(units, key=key_function)


def main():
    """Parses arguments and processes the specified file.

    Raises:
        IOError: An I/O error occurred with an input or output file.
        InputError: Input files lacked required fields.
    """
    # Set up argument parser.
    parser = argparse.ArgumentParser(description='Create translation files.')
    parser.add_argument(
        '--author',
        default='Ellen Spertus <ellen.spertus@gmail.com>',
        help='name and email address of contact for translators')
    parser.add_argument('--lang', default='en',
                        help='ISO 639-1 source language code')
    parser.add_argument('--output_dir', default='json',
                        help='relative directory for output files')
    parser.add_argument('--xlf', help='file containing xlf definitions')
    parser.add_argument('--templates', default=['template.soy'], nargs='+',
                        help='relative path to Soy templates, comma or space '
                        'separated (used for ordering messages)')
    global args
    args = parser.parse_args()

    # Make sure output_dir ends with slash.
    if (not args.output_dir.endswith(os.path.sep)):
      args.output_dir += os.path.sep

    # Process the input file, and sort the entries.
    units = _process_file(args.xlf)
    files = []
    for arg in args.templates:
      for filename in arg.split(','):
        filename = filename.strip();
        if filename:
          with open(filename) as myfile:
            files.append(' '.join(line.strip() for line in myfile))
    sorted_units = sort_units(units, ' '.join(files))

    # Write the output files.
    write_files(args.author, args.lang, args.output_dir, sorted_units, True)

    # Delete the input .xlf file.
    os.remove(args.xlf)
    print('Removed ' + args.xlf)


if __name__ == '__main__':
    main()
