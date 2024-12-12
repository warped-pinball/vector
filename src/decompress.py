import deflate
import json

def load_json_from_gzip(file_path, window_bits=6):
    """
    Load a JSON dictionary from a gzip-compressed .json.gz file.
    
    Parameters:
        file_path (str): The path to the gzip-compressed JSON file.
        window_bits (int): The window size parameter for DeflateIO. 
                           Adjust this to trade off between memory usage and 
                           speed/efficiency. Valid range is typically 8 to 15.
    
    Returns:
        dict: The decompressed JSON object as a dictionary.
    """
    try:
        # Open the compressed JSON file in binary read mode
        with open(file_path, 'rb') as compressed_file:
            # Create a DeflateIO stream in GZIP mode with the specified window_bits
            with deflate.DeflateIO(compressed_file, deflate.GZIP, window_bits) as decompressor:
                # Load the decompressed data directly as JSON
                data = json.load(decompressor)
        return data
    except Exception as e:
        print("Error loading JSON from gzip file:", e)
        raise

# load_json_from_gzip("config/all.json.gz", window_bits=11).keys()