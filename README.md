# Novium

This is a public transport software, similiar to what you would see at train stations. It pulls data from the BVG Departures using the [API provided by transport.rest](https://v6.bvg.transport.rest/). Made with Python 3.4 and works on Windows XP and up.

> [!CAUTION]
> This app was made purely for fun and is not really intended to be used commerically. If you want to use it publicly, please ensure you get permission by [BVG](https://developer.bvg.de/) first.

![App Screenshot](https://raw.githubusercontent.com/HauberRBLX/Novium/refs/heads/main/novium-screenshot.png)

## Compile it yourself

> [!NOTE]  
> If you are looking for compiled binaries, please go to the [Releases](https://github.com/HauberRBLX/Novium/releases) Tab.
> The following is mainly for developers to compile their own executables for Novium.

1. First off, please make sure that you have [Python 3.4.10](https://matejhorvat.si/en/windows/python/index.htm) installed as this is what the application was made with. Please also make sure you follow the installations instructions inside that folder.

2. Install all the required dependencies by running ``pip install -r requirements.txt``

3. Make any changes to the script as you desire

4. Compile it by opening the "compile.bat" script located in the root folder. If successful, the newly compiled binary will be available in the ```dist``` folder.

To run the app, please make sure you have the [Visual C++ 2010 Redistributales](https://download.microsoft.com/download/E/E/0/EE05C9EF-A661-4D9E-BCE2-6961ECDF087F/vcredist_x86.exe) installed. Otherwise the app will not run and will throw an error that  MSVCR100.dll was not found.

If you run into any issues, please open a bug report on the [Issues Tab](https://github.com/HauberRBLX/Novium/issues) with the "development" tag and provide a output of your console.

## Acknowledgements

 - [Readme.so Generator](https://readme.so)
 - [transport.rest](https://transport.rest)
