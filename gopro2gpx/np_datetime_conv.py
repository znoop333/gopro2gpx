"""
why is numpy being such a pain about converting np.datetime64 to/from datetime?
try out different options for time interpolation while preserving at least millisecond accuracy.
simple interpolation doesn't work as expected, see: https://stackoverflow.com/a/27939981/4051006
my problem with the answer there is that time.gmtime() and calendar.timegm() ignore fractions of a second!

more: https://stackoverflow.com/questions/13703720/converting-between-datetime-timestamp-and-datetime64
"""

import numpy as np
from scipy.io import savemat
from datetime import datetime, timedelta
from time import sleep
import unittest


def interp_time_array(x, xp, fp):
    """
    see https://numpy.org/doc/stable/reference/generated/numpy.interp.html for argument descriptions
    this helper allows fp to be datetimes, which np.interp() does not because it dies with:
    TypeError: Cannot cast array data from dtype('<M8[us]') to dtype('float64') according to the rule 'safe'

    according to https://numpy.org/doc/stable/reference/arrays.datetime.html , "Datetime Units"
    microsecond (us) resolution corresponds to a timespan of +/- 2.9e5 years, i.e., covering [290301 BC, 294241 AD]
    I think that's pretty safe for any video
    """
    my_epoch = np.array(fp[0], dtype='datetime64[us]')
    y = np.interp(x, xp, (fp - my_epoch).astype(float, casting='unsafe'))
    y1 = y.astype('timedelta64[us]', casting='unsafe') + my_epoch
    return y1  # will be numpy.array(dtype='datetime64[us]')


def testcase_data():
    t0 = datetime.now()
    sleep(0.3)
    t1 = datetime.now()
    dt = t1 - t0

    tms = np.zeros(3, dtype='datetime64[us]')
    tms[0] = t0
    tms[1] = t1
    tms[2] = t0 + 2 * dt

    return tms, t0


class TimeTestCases(unittest.TestCase):

    def testcase1(self):
        tms, t0 = testcase_data()
        ims2 = interp_time_array(np.linspace(0, 2, 5), np.arange(3), tms)
        self.assertEqual(len(ims2), 5)

    def testcase2(self):
        # this should fail. numpy is frustrating with datetime64.
        # I keep these errors to remind me of why writing a wrapper was necessary in the first place
        try:
            tms, t0 = testcase_data()
            # TypeError: Cannot cast array data from dtype('<M8[us]') to dtype('float64') according to the rule 'safe'
            ims = np.interp(np.linspace(0, 2, 5), np.arange(3), tms)

            # numpy.core._exceptions._UFuncBinaryResolutionError: ufunc 'subtract' cannot use operands with types dtype('<M8[us]') and dtype('O')
            epoch_sec = tms - t0

            # this works?! calculate microseconds since my epoch (first array value) but it stays inside numpy, i.e., it creates timedelta objects!
            epoch_ = np.array(t0, dtype='datetime64[us]')
            epoch_us = tms - epoch_
            ims = np.interp(np.linspace(0, 2, 5), np.arange(3), epoch_us.astype(float))
            float_us = ims.astype('timedelta64[us]', casting='unsafe') + epoch_

            epoch_us + np.array(t0, dtype='datetime64[us]')
        except:
            """ failed as expected. optional debug breakpoint below """
            self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
