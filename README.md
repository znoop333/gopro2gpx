# About klv_extraction

Python script that parses the gpmd stream for GOPRO moov track (MP4) and extract the GPS info into a CSV and kml file.  

Please note this differs from gopro2gpx.py: the metadata is directly read from the MP4 container, which means that ffmpeg does not need to be in the system PATH before running this program. The GPMF substream is automatically identified. The quaternions are automatically extracted, and a composite quaternion (camera+image) is created automatically for each frame. 

The outputs file formats are also different: a Matlab-compatible .MAT file is the primary output, and optional CSV files are generated for use with PIX4D or other programs.

# Installation

Install Anaconda from https://www.anaconda.com/products/individual

In Anaconda Prompt, run:
* conda create -y -n klv_extraction -c conda-forge   python scipy numpy av pillow
* conda activate klv_extraction
* pip install git+https://github.com/znoop333/gopro2gpx@master

# Launch Matlab from Conda environment

This is very important! Matlab will not find the correct python.exe in PATH unless the conda environment is activated first!

# Arguments and options

```
usage: klv_extraction.py [-h] [-v] [-k [OUTPUT_KML]] [-f [OUTPUT_FULL_CSV]]
                    [-p [OUTPUT_PIX4D_CSV]] [-n [MAX_FRAMES]] [-s]
                    video_file output_mat_file
positional arguments:
  video_file            GoPro Video file (.mp4)
  output_mat_file       output metadata .MAT file
options:
  -h, --help            show this help message and exit
  -l, --loglevel        Provide logging level. Example --loglevel debug or --loglevel warning
  -k [OUTPUT_KML], --output_kml [OUTPUT_KML]
                        output KML filename (optional)
  -f [OUTPUT_FULL_CSV], --output_full_csv [OUTPUT_FULL_CSV]
                        output filename for full metadata CSV (optional)
  -p [OUTPUT_PIX4D_CSV], --output_pix4d_csv [OUTPUT_PIX4D_CSV]
                        output filename for metadata CSV in PIX4D format
                        (optional)
  -n [MAX_FRAMES], --max_frames [MAX_FRAMES]
                        stop after processing N frames (optional)
  -s, --skip            Skip bad points (GPSFIX=0)
```  



