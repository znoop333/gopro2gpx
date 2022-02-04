import array
import logging
from pathlib import Path
import av
from klvdata import KLVData
import numpy as np
from scipy.io import savemat
from datetime import datetime, timedelta
from gopro2gpx import BuildGPSPoints

logger = logging.getLogger(__name__)


def parseStream(data_raw):
    """
    main code that reads the points
    """
    data = array.array('b')
    data.frombytes(data_raw)

    offset = 0
    klvlist = []

    while offset < len(data):

        klv = KLVData(data, offset)
        if klv.type == -1:
            # partial buffer read! save these bytes for later
            return klvlist, data_raw[offset:]

        if not klv.skip():
            klvlist.append(klv)
            # print(klv)
        else:
            if klv:
                print("Warning, skipping klv", klv)
            else:
                # unknown label
                pass

        offset += 8
        if klv.type != 0:
            offset += klv.padded_length
            # print(">offset:%d length:%d padded:%d" % (offset, length, padded_length))

    # if we get here, all KLV tags were completely read (no partial reads)
    return klvlist, bytes()


def read_video(source: Path, dest: Path, max_frames: int = None):
    frame_count = 0
    last_frame_with_metadata = -1
    unread_bytes = bytes()

    with av.open(str(source)) as container:
        n_frames = 16000  # container.streams.video[0].frames + 10
        frame_info = {
            'index': np.zeros(n_frames),
            'gps_time': np.zeros(n_frames, dtype='datetime64[us]'),
            'presentation_time': np.zeros(n_frames),
            'latitude': np.zeros(n_frames),
            'longitude': np.zeros(n_frames),
            'elevation': np.zeros(n_frames),
            'speed': np.zeros(n_frames)
        }

        # find the GPMF data stream
        gpmf_ix = -1
        for ix, ds in enumerate(container.streams.data):
            if 'GoPro MET' in ds.metadata['handler_name']:
                gpmf_ix = ix
                break
        if gpmf_ix == -1:
            raise f'GoPro Metadata stream not found in {source}'

        for packet_index, packet in enumerate(container.demux()):

            if max_frames is not None and frame_count >= max_frames:
                break

            # packet.stream.codec_context
            packet_data = packet.to_bytes()

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

            else:
                # logger.debug(f"No frames found in packet {packet_index}, processing as metadata")

                # if packet.stream.id != gpmf_ix:
                if 'GoPro MET' not in packet.stream.metadata['handler_name']:
                    continue

                klv, unread_bytes = parseStream(unread_bytes + packet_data)
                points = BuildGPSPoints(klv)

                if not len(points):
                    continue

                if last_frame_with_metadata >= 0:
                    frame_info['gps_time'][last_frame_with_metadata:frame_count + 1] = np.datetime64(points[0].time)
                else:
                    gps_count = len(points)
                    times = np.array([np.datetime64(p.time) for p in points], dtype='datetime64[us]')
                    dTime = (times-times[0]).astype(float)
                    lat = np.array([p.latitude for p in points])
                    lon = np.array([p.longitude for p in points])
                    speeds = np.array([p.speed for p in points])
                    interp_times = np.interp(np.arange(frame_count), np.arange(gps_count), dTime)
                    delta_times = list(map(lambda x: times[0]+timedelta(microseconds=x), interp_times))
                    #frame_info['gps_time'][:frame_count + 1] = np.datetime64(points[0].time)
                    frame_info['gps_time'][:frame_count + 1] = np.datetime64(times[0]+interp_times.astype('datetime64[us]'))

                last_frame_with_metadata = frame_count

                try:

                    1

                except Exception as err:
                    logger.error(f"Error decoding packet as metadata - exception", exc_info=True)

    # truncate unnecessary extra samples
    for k in frame_info:
        frame_info[k] = frame_info[k][:frame_count]

    savemat("metadata.mat", frame_info)


if __name__ == "__main__":
    read_video(Path(r"D:\djohnson\gopro\GH010198.MP4"), Path(r"D:\djohnson\gopro\frames"), 500)
    # read_video(Path(r"D:\djohnson\gopro\GH010198.MP4"), Path(r"D:\djohnson\gopro\frames"))
