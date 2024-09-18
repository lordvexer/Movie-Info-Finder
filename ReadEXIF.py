import ffmpeg
from tkinter import Tk, filedialog

def open_file():
    # Open a dialog to select a file
    root = Tk()
    root.withdraw()  # Hide the main window
    file_path = filedialog.askopenfilename(title="Select a file", 
                                           filetypes=[("All files", "*.*"), 
                                                      ("Video files", "*.mp4;*.avi;*.mkv;*.mov;*.flv"),
                                                      ("Image files", "*.jpg;*.jpeg;*.tiff;*.png;*.gif")])
    if not file_path:
        print("No file selected.")
        return None, None

    return file_path, file_path.split(".")[-1].lower()  # Return file path and extension


def read_video_metadata(file_path):
    try:
        # Get all metadata using ffmpeg probe
        metadata = ffmpeg.probe(file_path)

        # Print format information (general metadata about the file)
        print("--- File Format Metadata ---")
        format_info = metadata.get('format', {})
        for key, value in format_info.items():
            print(f"{key}: {value}")

        # Check for specific tags like director, producer, and writer
        if 'tags' in format_info:
            print("\n--- File Tags ---")
            tags = format_info['tags']
            
            # Look for Director, Producer, and Writer tags
            director = tags.get('director', 'Not available')
            producer = tags.get('Producer', 'Not available')
            writer = tags.get('writer', 'Not available')  # Sometimes stored under "writer"
            
            print(f"Director: {director}")
            print(f"Producer: {producer}")
            print(f"Writer: {writer}")
            
            # Print all available tags as well
            for tag_key, tag_value in tags.items():
                print(f"{tag_key}: {tag_value}")

        # Print stream-specific metadata (video, audio, etc.)
        print("\n--- Streams Metadata ---")
        for stream in metadata.get('streams', []):
            print(f"Stream Index: {stream.get('index')}")
            for key, value in stream.items():
                print(f"{key}: {value}")
            # Print custom tags in streams if available
            if 'tags' in stream:
                print("--- Custom Tags ---")
                for tag_key, tag_value in stream['tags'].items():
                    print(f"{tag_key}: {tag_value}")
            print()  # Add spacing between streams

    except FileNotFoundError:
        print("File not found.")
    except PermissionError:
        print("Permission denied.")
    except Exception as e:
        print(f"Error reading video metadata: {e}")


def main():
    file_path, file_type = open_file()
    if not file_path:
        return

    # If it's a video file, extract all available metadata
    print(f"Reading metadata from file: {file_path}")
    read_video_metadata(file_path)


# Run the program
if __name__ == "__main__":
    main()
