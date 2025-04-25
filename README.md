# TSV-TAS-2
A version of TSV-TAS for use with LunaKit

## Writing TSV-TAS Scripts
Read the tutorial [here](https://docs.google.com/document/d/1i1YwglNpgqvdOq_WdiWb-DzIf_UH0H0OAsYT_UibBBE/edit?usp=sharing).

## Generating Output File for TAS Mod
Make sure you have Python 3 installed.

### Local
In the command line, navigate to the ```TSV-TAS-2``` directory and enter ```python3 tsv-tas.py [path to input script file] [path to output file]```.

### FTP
If you want to send ouptut files to your Switch via FTP, first enter your FTP server configuration information in ```ftp_config.json```.

To generate and output file and send it to your Switch, in the command line, navigate to the ```TSV-TAS-2``` directory and enter ```python3 tsv-tas.py -f [path to input script file] [name of output file]```. The file will be transferred to the `scripts` directory of your Switch's SD card and will also be generated in the ```TSV-TAS-2``` directory on your computer.

### Debugging
If you would like to generate a debug CSV file displaying each frame of the generated output file, include the option ```-d``` before the path to the input script file (```-fd``` if you also want to use the FTP feature). The debug file will be generated in the ```TSV-TAS-2``` directory.

## Converting nx-TAS to TSV-TAS
To convert an nx-TAS script to a TSV-TAS script, in the command line, navigate to the ```TSV-TAS-2``` directory and enter ```python3 nx-tas-to-tsv-tas.py [path to nx-TAS file] [path to output file]```. (Note: functionality currently limited)

## Running the GUI

1. Place the generated `main_jp.exe` or `main_en.exe` in the same folder as `nx-tas-to-tsv-tas.py` and `tsv-tas.py`.
2. Double‑click the executable to launch the GUI.
3. In the GUI:
   - **Input Script File**: Browse and select your `.txt` or `.tsv` script.
   - **Output Directory**: Choose where the output files should be saved.
   - **Output File Name**: Base name (no extension) for the generated `.tsv` and binary files.
   - **Send via FTP** (optional): Check to enable, and enter your Switch FTP settings.
4. Click **Start Conversion**.
5. Conversion logs will appear in the GUI. On success, a message box confirms completion.

## Building the GUI Executable

Use PyInstaller to bundle into a single executable (**no console window**):

- **Japanese version (UI in Japanese)**
```
ppyinstaller --noconsole --onefile main_jp.py
```

- **English version (UI in English)**
```
pyinstaller --noconsole --onefile main_en.py
```

> **Note:** replace `main_jp.py` or `main_en.py` with your actual script filename.


## Disclaimer

Please note that this code was generated with the help of ChatGPT's Python code generation capabilities, and its correct operation is not guaranteed. Use at your own risk.
