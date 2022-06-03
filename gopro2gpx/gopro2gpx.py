#!/usr/bin/env python
#
# 17/02/2019
# Juan M. Casillas <juanm.casillas@gmail.com>
# https://github.com/juanmcasillas/gopro2gpx.git
#
# Released under GNU GENERAL PUBLIC LICENSE v3. (Use at your own risk)
#


import argparse
import array
import os
import platform
import re
import struct
import subprocess
import sys
import time
from collections import namedtuple
from datetime import datetime, timedelta
import logging

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(SCRIPT_DIR))

from .config import setup_environment
from . import fourCC
from . import gpmf
from . import gpshelper


def BuildGPSPoints(data, skip=False):
    """
    Data comes UNSCALED so we have to do: Data / Scale.
    Do a finite state machine to process the labels.
    GET
     - SCAL     Scale value
     - GPSF     GPS Fix
     - GPSU     GPS Time
     - GPS5     GPS Data
    """
    logger = logging.getLogger(__name__)

    points = []
    SCAL = fourCC.XYZData(1.0, 1.0, 1.0)
    GPSU = None
    SYST = fourCC.SYSTData(0, 0)

    stats = {
        'ok': 0,
        'badfix': 0,
        'badfixskip': 0,
        'empty': 0
    }

    GPSFIX = 0  # no lock.
    for d in data:

        if d.fourCC == 'SCAL':
            SCAL = d.data
        elif d.fourCC == 'GPSU':
            GPSU = d.data
            time_offset = timedelta(milliseconds=0)
        elif d.fourCC == 'GPSF':
            if d.data != GPSFIX:
                logger.debug("GPSFIX change to %s [%s]" % (d.data, fourCC.LabelGPSF.xlate[d.data]))
            GPSFIX = d.data
        elif d.fourCC == 'GPS5':
            # we have to use the REPEAT value.

            for item in d.data:

                if item.lon == item.lat == item.alt == 0:
                    logger.warning("Warning: Skipping empty point")
                    stats['empty'] += 1
                    continue

                if GPSFIX == 0:
                    stats['badfix'] += 1
                    if skip:
                        logger.warning("Warning: Skipping point due GPSFIX==0")
                        stats['badfixskip'] += 1
                        continue

                retdata = [float(x) / float(y) for x, y in zip(item._asdict().values(), list(SCAL))]

                time_offset = time_offset + timedelta(milliseconds=1000.0 / 18)

                gpsdata = fourCC.GPSData._make(retdata)
                p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, GPSU + time_offset, gpsdata.speed)
                points.append(p)
                stats['ok'] += 1

        elif d.fourCC == 'SYST':
            data = [float(x) / float(y) for x, y in zip(d.data._asdict().values(), list(SCAL))]
            if data[0] != 0 and data[1] != 0:
                SYST = fourCC.SYSTData._make(data)


        elif d.fourCC == 'GPRI':
            # KARMA GPRI info

            if d.data.lon == d.data.lat == d.data.alt == 0:
                logger.warning("Warning: Skipping empty point")
                stats['empty'] += 1
                continue

            if GPSFIX == 0:
                stats['badfix'] += 1
                if skip:
                    logger.warning("Warning: Skipping point due GPSFIX==0")
                    stats['badfixskip'] += 1
                    continue

            data = [float(x) / float(y) for x, y in zip(d.data._asdict().values(), list(SCAL))]
            gpsdata = fourCC.KARMAGPSData._make(data)

            if SYST.seconds != 0 and SYST.miliseconds != 0:
                p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, datetime.fromtimestamp(SYST.miliseconds),
                                       gpsdata.speed)
                points.append(p)
                stats['ok'] += 1

    logger.info("-- stats -----------------")
    total_points = 0
    for i in stats.keys():
        total_points += stats[i]
    logger.info("- Ok:              %5d" % stats['ok'])
    logger.info("- GPSFIX=0 (bad):  %5d (skipped: %d)" % (stats['badfix'], stats['badfixskip']))
    logger.info("- Empty (No data): %5d" % stats['empty'])
    logger.info("Total points:      %5d" % total_points)
    logger.info("--------------------------")
    return (points)


def BuildOrientations(data):
    """
    Data comes UNSCALED so we have to do: Data / Scale.
    Do a finite state machine to process the labels.
    GET
     - SCAL     Scale value
     - CORI     Camera ORIentation: Quaternions for the camera orientation since capture start
     - IORI     Image ORIentation: Quaternions for the image orientation relative to the camera body
    """

    points_CORI = []
    points_IORI = []
    SCAL = 1

    for d in data:
        if d.fourCC == 'SCAL':
            SCAL = d.data
        elif d.fourCC == 'CORI' or d.fourCC == 'IORI':
            # use the REPEAT value. multiple quaternions may be reported in one packet

            for item in d.data:
                retdata = [ float(x) / float(SCAL) for x in item._asdict().values() ]

                qdata = fourCC.QUATData._make(retdata)
                if d.fourCC == 'CORI':
                    points_CORI.append(qdata)
                else:
                    points_IORI.append(qdata)

    return points_CORI, points_IORI

def parseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="count")
    parser.add_argument("-b", "--binary", help="read data from bin file", action="store_true")
    parser.add_argument("-s", "--skip", help="Skip bad points (GPSFIX=0)", action="store_true", default=False)
    parser.add_argument("file", help="Video file or binary metadata dump")
    parser.add_argument("outputfile", help="output file. builds KML and GPX")
    args = parser.parse_args()

    return args

def main():
    args = parseArgs()
    config = setup_environment(args)
    parser = gpmf.Parser(config)

    if not args.binary:
        data = parser.readFromMP4()
    else:
        data = parser.readFromBinary()

    # build some funky tracks from camera GPS

    points = BuildGPSPoints(data, skip=args.skip)

    if len(points) == 0:
        print("Can't create file. No GPS info in %s. Exitting" % args.file)
        sys.exit(0)

    my_csv = gpshelper.generate_CSV(points)
    with open("%s.csv" % args.outputfile , "w+") as fd:
        fd.write(my_csv)

    return

    kml = gpshelper.generate_KML(points)
    with open("%s.kml" % args.outputfile , "w+") as fd:
        fd.write(kml)

    gpx = gpshelper.generate_GPX(points, trk_name="gopro7-track")
    with open("%s.gpx" % args.outputfile , "w+") as fd:
        fd.write(gpx)

if __name__ == "__main__":
    main()
