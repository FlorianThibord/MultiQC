#!/usr/bin/env python

""" MultiQC submodule to parse output from Picard MarkDuplicates """

from collections import OrderedDict
import logging
import os
import re

from multiqc.plots import bargraph

# Initialise the logger
log = logging.getLogger(__name__)


def parse_reports(self,
    log_key='picard/markdups',
    section_name='Mark Duplicates',
    section_anchor='picard-markduplicates',
    plot_title='Picard: Deduplication Stats',
    plot_id='picard_deduplication',
    data_filename='multiqc_picard_dups'):
    """ Find Picard MarkDuplicates reports and parse their dataself.
    This function is also used by the biobambam2 module, hence the parameters.
    """

    # Set up vars
    self.picard_dupMetrics_data = dict()

    # Go through logs and find Metrics
    for f in self.find_log_files(log_key, filehandles=True):
        s_name = f['s_name']
        for l in f['f']:
            # New log starting
            if 'markduplicates' in l.lower() and 'input' in l.lower():
                s_name = None

                # Pull sample name from input
                fn_search = re.search(r"INPUT(?:=|\s+)(\[?[^\s]+\]?)", l, flags=re.IGNORECASE)
                if fn_search:
                    s_name = os.path.basename(fn_search.group(1).strip('[]'))
                    s_name = self.clean_s_name(s_name, f['root'])

            if s_name is not None:
                if 'UNPAIRED_READ_DUPLICATES' in l:
                    if s_name in self.picard_dupMetrics_data:
                        log.debug("Duplicate sample name found in {}! Overwriting: {}".format(f['fn'], s_name))
                    self.add_data_source(f, s_name, section='DuplicationMetrics')
                    self.picard_dupMetrics_data[s_name] = dict()
                    keys = l.rstrip("\n").split("\t")
                    vals = f['f'].readline().rstrip("\n").split("\t")
                    for i, k in enumerate(keys):
                        try:
                            self.picard_dupMetrics_data[s_name][k] = float(vals[i])
                        except ValueError:
                            self.picard_dupMetrics_data[s_name][k] = vals[i]
                    # Check that this sample had some reads
                    if self.picard_dupMetrics_data[s_name].get('READ_PAIRS_EXAMINED', 0) == 0 and \
                       self.picard_dupMetrics_data[s_name].get('UNPAIRED_READS_EXAMINED', 0) == 0:
                        self.picard_dupMetrics_data.pop(s_name, None)
                        log.warn("Skipping MarkDuplicates sample '{}' as log contained no reads".format(s_name))
                    s_name = None

        for s_name in list(self.picard_dupMetrics_data.keys()):
            if len(self.picard_dupMetrics_data[s_name]) == 0:
                self.picard_dupMetrics_data.pop(s_name, None)
                log.debug("Removing {} as no data parsed".format(s_name))


    # Filter to strip out ignored sample names
    self.picard_dupMetrics_data = self.ignore_samples(self.picard_dupMetrics_data)

    if len(self.picard_dupMetrics_data) > 0:

        # Write parsed data to a file
        self.write_data_file(self.picard_dupMetrics_data, data_filename)

        # Add to general stats table
        self.general_stats_headers['PERCENT_DUPLICATION'] = {
            'title': '% Dups',
            'description': '{} - Percent Duplication'.format(section_name),
            'max': 100,
            'min': 0,
            'suffix': '%',
            'scale': 'OrRd',
            'modify': lambda x: self.multiply_hundred(x)
        }
        for s_name in self.picard_dupMetrics_data:
            if s_name not in self.general_stats_data:
                self.general_stats_data[s_name] = dict()
            self.general_stats_data[s_name].update( self.picard_dupMetrics_data[s_name] )

        # Make the bar plot and add to the MarkDuplicates section
        #
        # The table in the Picard metrics file contains some columns referring
        # read pairs and some referring to single reads.
        for s_name, metr in self.picard_dupMetrics_data.items():
            metr["READS_IN_DUPLICATE_PAIRS"]    = 2.0 * metr["READ_PAIR_DUPLICATES"]
            metr["READS_IN_UNIQUE_PAIRS"]       = 2.0 * (metr["READ_PAIRS_EXAMINED"] - metr["READ_PAIR_DUPLICATES"])
            metr["READS_IN_UNIQUE_UNPAIRED"]    = metr["UNPAIRED_READS_EXAMINED"] - metr["UNPAIRED_READ_DUPLICATES"]
            metr["READS_IN_DUPLICATE_PAIRS_OPTICAL"] = 2.0 * metr["READ_PAIR_OPTICAL_DUPLICATES"]
            metr["READS_IN_DUPLICATE_PAIRS_NONOPTICAL"] = metr["READS_IN_DUPLICATE_PAIRS"] - metr["READS_IN_DUPLICATE_PAIRS_OPTICAL"]
            metr["READS_IN_DUPLICATE_UNPAIRED"] = metr["UNPAIRED_READ_DUPLICATES"]
            metr["READS_UNMAPPED"]              = metr["UNMAPPED_READS"]

        keys = OrderedDict()
        keys_r = [
            'READS_IN_UNIQUE_PAIRS',
            'READS_IN_UNIQUE_UNPAIRED',
            'READS_IN_DUPLICATE_PAIRS_OPTICAL',
            'READS_IN_DUPLICATE_PAIRS_NONOPTICAL',
            'READS_IN_DUPLICATE_UNPAIRED',
            'READS_UNMAPPED'
        ]
        for k in keys_r:
            keys[k] = {'name': k.replace('READS_', '').replace('IN_', '').replace('_',' ').title()}

        # Config for the plot
        pconfig = {
            'id': plot_id,
            'title': plot_title,
            'ylab': '# Reads',
            'cpswitch_counts_label': 'Number of Reads',
            'cpswitch_c_active': False
        }

        self.add_section (
            name = section_name,
            anchor = section_anchor,
            description = 'Number of reads, categorised by duplication state. **Pair counts are doubled** - see help text for details.',
            helptext = '''
            The table in the Picard metrics file contains some columns referring
            read pairs and some referring to single reads.

            To make the numbers in this plot sum correctly, values referring to pairs are doubled
            according to the scheme below:

            * `READS_IN_DUPLICATE_PAIRS = 2 * READ_PAIR_DUPLICATES`
            * `READS_IN_UNIQUE_PAIRS = 2 * (READ_PAIRS_EXAMINED - READ_PAIR_DUPLICATES)`
            * `READS_IN_UNIQUE_UNPAIRED = UNPAIRED_READS_EXAMINED - UNPAIRED_READ_DUPLICATES`
            * `READS_IN_DUPLICATE_PAIRS_OPTICAL = 2 * READ_PAIR_OPTICAL_DUPLICATES`
            * `READS_IN_DUPLICATE_PAIRS_NONOPTICAL = READS_IN_DUPLICATE_PAIRS - READS_IN_DUPLICATE_PAIRS_OPTICAL`
            * `READS_IN_DUPLICATE_UNPAIRED = UNPAIRED_READ_DUPLICATES`
            * `READS_UNMAPPED = UNMAPPED_READS`
            ''',
            plot = bargraph.plot(self.picard_dupMetrics_data, keys, pconfig)
        )

    # Return the number of detected samples to the parent module
    return len(self.picard_dupMetrics_data)
