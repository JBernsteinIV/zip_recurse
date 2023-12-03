#!/usr/bin/env python3
# Name: zip_extractor.py
# Author: John L. Bernstein IV
# Date: 2023-12-02
# Version: 1.0.0
""" Standard library dependencies """
from functools import (wraps)  # To manage decorator functions.
from shutil import (which)     # Shell utilities like the which command so we aren't reinventing the wheel.
import time                    # Keep track of timers
import io                      # For reading/writing to file, streams, and sockets.
import json                    # To parse and load JSON data from an API.
import os                      # Get access to certain utilities like cwd.
import pathlib                 # For managing directories.
import mimetypes               # To manage checking file types of expected inputs to functions.
import subprocess              # To invoke /bin/sh shells to run commands.
import sys                     # To handle exit codes.
import signal                  # To handle timeouts.
import zipfile                 # To manage zip files; this is part of Python 3.6 stdlib.

GLOBAL_TIMEOUT=1800

# Define a timer to determine how long each task runs for.
def timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        end = time.time()
        duration = round(end - start,2)
        print(f"{func.__name__} took {duration} seconds to run")
        return result
    return wrapper

def timeout(seconds):
    def process_timeout(func):
        def handle_timeout(signum, frame):
            raise TimeoutError("function %s timed out" % func)

        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, handle_timeout)
            signal.alarm(seconds)

            try:
                func(*args, **kwargs)
            finally:
                signal.alarm(0) # No need to time out!

        return wrapper

    return process_timeout

# Args for positional arguments (0,1,2,3,..), kwargs for keyword arguments(e.g. input=stuff, output=other_stuff).
def run(*args, **kwargs):
    # Invoke a new piped process to redirect the output into a new process so Python can read it.
    output = subprocess.run(*args,stdout=subprocess.PIPE,timeout=GLOBAL_TIMEOUT)
    return output

def dmidecode(string):
    # Valid keywords for the -s option of dmidecode.
    valid_keywords = [
        'bios-vendor','bios-version','bios-release-date',
        'system-manufacturer','system-product-name','system-version','system-serial-number','system-uuid',
        'baseboard-manufacturer','baseboard-product-name','baseboard-version','baseboard-serial-number','baseboard-asset-tag',
        'chassis-manufacturer', 'chassis-type','chassis-version','chassis-serial-number','chassis-asset-tag',
        'processor-family','processor-manufacturer','processor-version','processor-frequency'
    ]
    if string not in valid_keywords:
        print("Error: %s is not a valid keyword" % string)
        return None
    dmidecode = which('dmidecode')
    command   = [dmidecode, '-s', string]
    output    = run(command)
    return output.stdout.decode('utf-8').strip()

def get_bios_version():
    return dmidecode('bios-version')

def get_manufacturer():
    return dmidecode('baseboard-manufacturer')

def get_product_name():
    return dmidecode('system-product-name')

def extract(filename):
    cwd = os.getcwd()
    expected_type = 'application/zip'
    # Check for the correct file type. Exit early if not a zip file.
    if mimetypes.guess_type(filename)[0] != expected_type:
        return None
    z = zipfile.ZipFile(filename)
    for f in z.namelist():
        # For file that are not also zip files, skip.
        if mimetypes.guess_type(f)[0] != expected_type:
            continue
        # get directory name from file
        dirname = "".join(os.path.splitext(f)[0].split("/")[:-1])
        # create new directory
        pathlib.Path(dirname).mkdir(parents=True, exist_ok=True)
        # read inner zip file into bytes buffer
        content = io.BytesIO(z.read(f))
        zip_file = zipfile.ZipFile(content)
        for i in zip_file.namelist():
            zip_file.extract(i, dirname)
    else:
        z.extractall()
    result = ["".join("%s/%s" % (cwd,res)) for res in z.namelist()]
    return result

@timer
@timeout(seconds=GLOBAL_TIMEOUT)
def run_utility(utility):
    # Run the subprocess in the background
    p = subprocess.Popen([utility], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Read from the file until the background process finishes
    while True:
        with open('/tmp/output.log','a') as output:
            line = p.stdout.readline()
            if not line:
                break
            output.write(line.decode('utf-8'))
            print(line.decode("utf-8"))
    # Wait for the background process to finish
    p.wait()

# Helper utility to get the index of a zip file in ls output.
# Credit to John La Rooy for the solution
# Source: https://stackoverflow.com/questions/2170900/get-first-list-index-containing-sub-string
def first_substring(strings, substring):
    return next(i for i, string in enumerate(strings) if substring in string)

def get_manufacturer_utility(manufacturer):
    if manufacturer == "Gigabyte Technology Co., Ltd.":
        return 'socflash_Update.sh'
    return None

if __name__ == '__main__':
    version      = get_bios_version()
    manufacturer = get_manufacturer()
    product_name = get_product_name()
    cwd          = os.getcwd()
    # Find the zip file in our current working directory.
    filename = [f for f in run(['/bin/ls','-l']).stdout.decode('utf-8').split() if product_name in f]
    result   = None
    utility  = get_manufacturer_utility(manufacturer)
    if utility == None:
        print("%s is not currently supported for this script! Exiting..." % manufacturer)
        sys.exit(1)
    if (len(filename) > 0):
        _filename = filename[first_substring(filename,'.zip')]
        result = extract(_filename)
    if result is None:
        print("%s is not currently supported for this script! Exiting..." % product_name)
        sys.exit(1)
    for res in result:
            if not os.path.isdir(res):
                continue
            # Search all unzipped directories for the utility script specified above.
            for root, dirs, files in os.walk(cwd):
                if utility in files:
                    utility = root + "/" + files[first_substring(files, utility)]
                    os.chmod(utility, 0o775)
                    run_utility(utility=utility)
                    break