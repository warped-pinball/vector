# compression step from sync.py
def compress_to_gzip(
    input_filepath, output_filepath=None, window_bits=9, compress_level=9
):
    """
    Compress a file into GZIP format using zlib with a specified window size and compression level.

    Parameters:
        input_filepath (str): The path to the input file to compress.
        output_filepath (str, optional): The path to the output compressed file. Defaults to input_filepath + '.gz'.
        window_bits (int): The base-2 logarithm of the window size. Valid range is 8 to 15.
                           Adding 16 to this value will produce a GZIP header,
                           e.g., 16 + 9 = 25 yields GZIP with ~512-byte window.
        compress_level (int): Compression level (1=fastest, 9=slowest but most compressed).

    Returns:
        None
    """
    if output_filepath is None:
        output_filepath = input_filepath + ".gz"

    with open(input_filepath, "rb") as f_in:
        data_bytes = f_in.read()

    compressor = zlib.compressobj(
        level=compress_level, method=zlib.DEFLATED, wbits=16 + window_bits
    )

    compressed_data = compressor.compress(data_bytes) + compressor.flush()

    with open(output_filepath, "wb") as f_out:
        f_out.write(compressed_data)

    # remove the original file
    os.remove(input_filepath)

    # decomresstion on pico


import json

import deflate


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
        with open(file_path, "rb") as compressed_file:
            # Create a DeflateIO stream in GZIP mode with the specified window_bits
            with deflate.DeflateIO(
                compressed_file, deflate.GZIP, window_bits
            ) as decompressor:
                # Load the decompressed data directly as JSON
                data = json.load(decompressor)
        return data
    except Exception as e:
        print("Error loading JSON from gzip file:", e)
        raise


# load_json_from_gzip("config/all.json.gz", window_bits=11).keys()
