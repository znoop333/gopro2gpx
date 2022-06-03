import argparse
import array
import logging
import sys
from pathlib import Path
import av
from .klvdata import KLVData
import numpy as np
from scipy.io import savemat
from datetime import datetime, timedelta
from gopro2gpx.gopro2gpx import BuildGPSPoints, BuildOrientations
from .np_datetime_conv import interp_time_array
import csv
import math
from av.data.stream import DataStream
from av.video.stream import VideoStream
from scipy.spatial.transform import Rotation as R
from . import gpshelper



def parseStream(data_raw):
    """
    main code that reads the points
    """
    data = array.array('b')
    data.frombytes(data_raw)

    offset = 0
    klvlist = []
    logger = logging.getLogger(__name__)

    while offset < len(data):

        klv = KLVData(data, offset)
        if klv.type == -1:
            # partial buffer read! save these bytes for later
            return klvlist, data_raw[offset:]

        if not klv.skip():
            klvlist.append(klv)
            if klv.fourCC == "STNM":
                logger.debug(klv)
        else:
            if klv:
                logger.warning(f"Warning, skipping klv {klv}")
            else:
                logger.warning(f"Warning, unknown label!")

        offset += 8
        if klv.type != 0:
            offset += klv.padded_length
            # print(">offset:%d length:%d padded:%d" % (offset, length, padded_length))

    # if we get here, all KLV tags were completely read (no partial reads)
    return klvlist, bytes()


def read_video(args):
    source = args.video_file
    max_frames = args.max_frames
    frame_count = 0
    last_frame = 0
    unread_bytes = bytes()
    all_points = []

    logger = logging.getLogger(__name__)

    logger.info(f'Opening video file {str(source)}')
    with av.open(str(source)) as container:
        n_frames = container.streams.video[0].frames
        logger.debug(f'Frame count: {n_frames}')
        frame_info = {
            'index': np.zeros(n_frames),
            'gps_time': np.zeros(n_frames, dtype='datetime64[us]'),
            'presentation_time': np.zeros(n_frames),
            'latitude': np.zeros(n_frames),
            'longitude': np.zeros(n_frames),
            'elevation': np.zeros(n_frames),
            'speed': np.zeros(n_frames),
            'c_qw': np.zeros(n_frames),
            'c_qx': np.zeros(n_frames),
            'c_qy': np.zeros(n_frames),
            'c_qz': np.zeros(n_frames),
            'i_qw': np.zeros(n_frames),
            'i_qx': np.zeros(n_frames),
            'i_qy': np.zeros(n_frames),
            'i_qz': np.zeros(n_frames)
        }
        cori = []
        iori = []

        # find the GPMF data stream
        gpmf_ix = -1
        for ix, ds in enumerate(container.streams.data):
            if 'GoPro MET' in ds.metadata['handler_name']:
                gpmf_ix = ix
                break
        if gpmf_ix == -1:
            raise Exception(f'GoPro Metadata stream not found in {str(source)}')

        for packet_index, packet in enumerate(container.demux()):

            if packet.dts is None:
                # We need to skip the "flushing" packets that `demux` generates
                continue

            if max_frames is not None and frame_count >= max_frames:
                break

            """
            we have to handle the different streams separately:
                we need to count the video frames in the video stream
                we don't care about the audio stream(s)
                we want to parse the GPMF metadata stream but not the other data streams
            we should avoid decoding the packets if we don't really need to process them
            """

            if isinstance(packet.stream, VideoStream):
                frames = packet.decode()
                if frames is not None and len(frames) > 0:
                    for frame in frames:
                        last_frame_pts = frame.pts
                        frame_info['index'][frame_count] = frame.index
                        frame_info['presentation_time'][frame_count] = frame.time

                        """
                        image_data = frame.to_image()
                        image_size = image_data.size
                        if image_size[0] != 320:
                            frame_meta = {}
                            frame_meta["frame_timestamp_int"] = frame.pts
                            frame_meta["frame_time"] = frame.time
                            frame_meta["frame_index"] = frame.index
                            frame_meta["packet_index"] = packet_index
                            frame_meta["is_corrupt"] = frame.is_corrupt
                            frame_meta["key_frame"] = frame.key_frame
                            frame_meta["packet_size"] = packet.size
                            frame_meta["num_frames_in_packet"] = len(frames)
                            frame_meta["packet_stream_average_rate"] = packet.stream.average_rate
                            frame_meta["frame_image_width"] = image_size[0]
                            frame_meta["frame_image_height"] = image_size[1]
                        """
                        frame_count += 1

            elif isinstance(packet.stream, DataStream):
                # logger.debug(f"No frames found in packet {packet_index}, processing as metadata")

                # there are multiple data streams, but we only care about the metadata stream with the GPMF data
                if 'GoPro MET' not in packet.stream.metadata['handler_name']:
                    continue

                packet_data = packet.to_bytes()
                klv, unread_bytes = parseStream(unread_bytes + packet_data)
                points = BuildGPSPoints(klv, skip=args.skip)
                all_points.extend(points)
                points_CORI, points_IORI = BuildOrientations(klv)
                cori.extend(points_CORI)
                iori.extend(points_IORI)

                if not len(points):
                    continue

                gps_count = len(points)
                if gps_count > 0:
                    times = np.array([np.datetime64(p.time) for p in points], dtype='datetime64[us]')
                    lat = np.array([p.latitude for p in points])
                    lon = np.array([p.longitude for p in points])
                    speeds = np.array([p.speed for p in points])
                    elevation = np.array([p.elevation for p in points])

                    # assume that the video runs at 29.97 Hz and the GPS runs at 18 Hz.
                    # the easiest way to line these up is with simple interpolation.
                    x = np.linspace(0, 1, frame_count - last_frame)
                    xp = np.linspace(0, 1, gps_count)

                    frame_info['gps_time'][last_frame:frame_count] = interp_time_array(x, xp, times)

                    # interpolating latitude and longitude independently isn't really the right thing to do,
                    # but let's see if it's adequate here
                    frame_info['latitude'][last_frame:frame_count] = np.interp(x, xp, lat)
                    frame_info['longitude'][last_frame:frame_count] = np.interp(x, xp, lon)
                    frame_info['speed'][last_frame:frame_count] = np.interp(x, xp, speeds)
                    frame_info['elevation'][last_frame:frame_count] = np.interp(x, xp, elevation)

                    if len(points_CORI) > 0:
                        frame_info['c_qw'][last_frame:frame_count] = [p.qw for p in points_CORI]
                        frame_info['c_qx'][last_frame:frame_count] = [p.qx for p in points_CORI]
                        frame_info['c_qy'][last_frame:frame_count] = [p.qy for p in points_CORI]
                        frame_info['c_qz'][last_frame:frame_count] = [p.qz for p in points_CORI]

                    if len(points_IORI) > 0:
                        frame_info['i_qw'][last_frame:frame_count] = [p.qw for p in points_IORI]
                        frame_info['i_qx'][last_frame:frame_count] = [p.qx for p in points_IORI]
                        frame_info['i_qy'][last_frame:frame_count] = [p.qy for p in points_IORI]
                        frame_info['i_qz'][last_frame:frame_count] = [p.qz for p in points_IORI]

                last_frame = frame_count

    # truncate unnecessary extra samples: corrupted video frames could reduce the total number of frames we could save
    if frame_count < n_frames:
        for k in frame_info:
            frame_info[k] = frame_info[k][:frame_count]

    logger.info(f'Finished reading {frame_count} frames from {str(source)}')

    # interpret the quaternions
    qn_iori = [R.from_quat([p.qw, p.qx, p.qy, p.qz]) for p in iori]
    qn_cori = [R.from_quat([p.qw, p.qx, p.qy, p.qz]) for p in cori]

    # IORI is relative to CORI, and I want the net quaternion describing the image pose
    qn_net = [q_i.inv() * q_c for q_c, q_i in zip(qn_cori, qn_iori)]

    # the initial GoPro pose is set when the device is powered on, and all quaternions are relative to that.
    # but since I cannot know that initial pose (most GoPros do not have a magnetometer), I'm going to
    # save the Euler angles relative to that initial pose
    rel_net_angles = np.array(
        [(qn_net[ii] * qn_net[0].inv()).as_euler('yxz', degrees=True) for ii in range(frame_count)])
    frame_info['rel_net_az'] = rel_net_angles[:, 0]
    frame_info['rel_net_tilt'] = rel_net_angles[:, 1]
    frame_info['rel_net_roll'] = rel_net_angles[:, 2]

    rel_cori = np.array([(qn_cori[ii] * qn_cori[0].inv()).as_euler('yxz', degrees=True) for ii in range(frame_count)])
    frame_info['cam_rel_az'] = rel_cori[:, 0]
    frame_info['cam_rel_tilt'] = rel_cori[:, 1]
    frame_info['cam_rel_roll'] = rel_cori[:, 2]

    rel_iori = np.array([(qn_iori[ii] * qn_iori[0].inv()).as_euler('yxz', degrees=True) for ii in range(frame_count)])
    frame_info['img_rel_az'] = rel_iori[:, 0]
    frame_info['img_rel_tilt'] = rel_iori[:, 1]
    frame_info['img_rel_roll'] = rel_iori[:, 2]

    # save in Matlab format
    if args.output_mat_file is None:
        args.output_mat_file = args.video_file.with_suffix(".mat")
    logger.info(f'Writing .MAT file: {str(args.output_mat_file)}')
    savemat(str(args.output_mat_file), frame_info)

    if args.output_full_csv is None:
        args.output_full_csv = args.video_file.with_suffix(".csv")

    if args.output_full_csv:
        # save the full metadata as a CSV just in case somebody wants that for another (non-Matlab program)
        logger.info(f'Writing full .CSV file: {str(args.output_full_csv)}')
        with args.output_full_csv.open('w', newline='') as csvfile:
            fieldnames = frame_info.keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, dialect="excel")
            writer.writeheader()

            # from dict of lists to list of dicts
            rows = [{k: v[ii] for k, v in frame_info.items()} for ii in range(frame_count)]
            for ii in range(frame_count):
                writer.writerow(rows[ii])

    """
write the CSV for PIX4D to use (Image geolocation file)

from PIX4Dmapper Input files on https://support.pix4d.com/hc/en-us/articles/202558539-Input-files#label2

WGS84 geographic coordinates
imagename,latitude [decimal degrees],longitude [decimal degrees],altitude [meter]

For geographic WGS84 (latitude, longitude, altitude) image geolocation coordinates. The file is a .csv, .txt, or .dat 
extension file. It contains four columns per line, and uses a comma to separate the characters.

Example:
IMG_3165.JPG,46.2345612,6.5611445,539.931234
IMG_3166.JPG,46.2323423,6.5623423,529.823423
    """
    if args.output_pix4d_csv:
        logger.info(f'Writing PIX4D .CSV file: {str(args.output_pix4d_csv)}')
        with args.output_pix4d_csv.open('w', newline='') as csvfile:
            fieldnames = ['imagename', 'latitude', 'longitude', 'altitude']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter=',', quoting=csv.QUOTE_NONE)
            writer.writeheader()

            # determine how many prefix zeros will be required to keep these files in order
            n_digits_required = math.ceil(math.log10(frame_count))

            for ii in range(frame_count):
                index = int(frame_info["index"][ii] + 1)  # does PIX4D count frames from 0 or 1? I guess 1
                index_str = str(index).zfill(n_digits_required)
                writer.writerow(
                    {'imagename': f'IMG_{index_str}.JPG',
                     'latitude': frame_info['latitude'][ii],
                     'longitude': frame_info['longitude'][ii],
                     'altitude': frame_info['elevation'][ii]
                     }
                )

    if args.output_kml:
        logger.info(f'Writing .KML file: {str(args.output_kml)}')
        # oops, these altitudes don't seem to work right in Google Earth, so I'm going to set them all to 0
        for ii in range(len(all_points)):
            all_points[ii].elevation = 0
        kml = gpshelper.generate_KML(all_points)
        with args.output_kml.open("w+") as fd:
            fd.write(kml)


def parseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("-k", "--output_kml", nargs='?', type=Path, help="output KML filename (optional)")
    parser.add_argument("-f", "--output_full_csv", nargs='?', type=Path,
                        help="output filename for full metadata CSV (optional)")
    parser.add_argument("-p", "--output_pix4d_csv", nargs='?', type=Path,
                        help="output filename for metadata CSV in PIX4D format (optional)")
    parser.add_argument("-n", "--max_frames", nargs='?', type=int, help="stop after processing N frames (optional)")
    parser.add_argument("-s", "--skip", help="Skip bad points (GPSFIX=0)", action="store_true", default=False)
    parser.add_argument('-l', '--loglevel', default='warning',
                        help='Provide logging level. Example --loglevel debug')
    parser.add_argument("-m", "--output_mat_file", help="output metadata .MAT file (optional)", type=Path)
    parser.add_argument("video_file", help="GoPro Video file (.mp4)", type=Path)

    # parser.print_help()
    args = parser.parse_args()

    return args


def main():
    args = parseArgs()
    logging.basicConfig(level=args.loglevel.upper())
    logger = logging.getLogger(__name__)
    read_video(args)
    logger.info(f'Finished working on {str(args.video_file)}. Exiting')


if __name__ == "__main__":
    main()
