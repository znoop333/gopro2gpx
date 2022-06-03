# About klv_extraction

Python script that parses the gpmd stream for GOPRO moov track (MP4) and extract the GPS info into a CSV and kml file.  

Please note this differs from gopro2gpx.py: the metadata is directly read from the MP4 container, which means that ffmpeg does not need to be in the system PATH before running this program. The GPMF substream is automatically identified. The quaternions are automatically extracted, and a composite quaternion (camera+image) is created automatically for each frame. 

The outputs file formats are also different: a Matlab-compatible .MAT file is the primary output, and optional CSV files are generated for use with PIX4D or other programs.

# Installation

Install Anaconda from https://www.anaconda.com/products/individual

In Anaconda Prompt, run:
* conda create -y -n klv_extraction -c conda-forge -c anaconda    python scipy numpy av pillow git pip
* conda activate klv_extraction
* pip install git+https://github.com/znoop333/gopro2gpx@master

# Launch Matlab from Conda environment

This is very important! Matlab will not find the correct python.exe in PATH unless the conda environment is activated first!

# Arguments and options

```
usage: 
python -c "from gopro2gpx.klv_extraction import main; main()" [-h] [-v] [-k [OUTPUT_KML]] [-f [OUTPUT_FULL_CSV]]
                    [-p [OUTPUT_PIX4D_CSV]] [-n [MAX_FRAMES]] [-s] [-m [output_mat_file]]
                    video_file 

positional arguments:
  video_file            GoPro Video file (.mp4)
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
  -m output_mat_file    output metadata .MAT file in Matlab HDF5 format
  -s, --skip            Skip bad points (GPSFIX=0)
```  

# Example of running this script to create a CSV file

```  
For example, if the video file was in "D:\data\GH010198.MP4", you can run a command like this:

conda activate klv_extraction
cd /d D:\data
python -c "from gopro2gpx.klv_extraction import main; main()" -f GH010198.csv GH010198.MP4 GH010198.mat
```  




