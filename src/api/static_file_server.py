import os
import gc

from Utilities.ls import ls

def get_content_type(file_path):
    content_type_mapping = {
        '.gz': 'application/gzip',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.html': 'text/html',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif'
    }
    for extension, content_type in content_type_mapping.items():
        if file_path.endswith(extension):
            return content_type
    return 'application/octet-stream'


# define streaming file service route
def serve_file(file_path):
    def route(request):
        print(f"Attempting to serve file @ {file_path}")
        try:
            headers = {
                'Content-Type': get_content_type(file_path),
                'Connection': 'close'
            }

            def file_stream_generator():
                gc.collect()
                with open(file_path, 'rb') as f:
                    while True:
                        chunk = f.read(1024)  # Read in chunks of 1KB
                        if not chunk:
                            break
                        yield chunk
                gc.collect() 

            print("File opened successfully")
            return file_stream_generator(), 200, headers

        except OSError as e:
            error_message = "File Not Found" if e.errno == 2 else "Internal Server Error"
            print(f"Error: {error_message} - {e}")
            gc.collect()
            return f"<html><body><h1>{error_message}</h1></body></html>", 404 if e.errno == 2 else 500, {'Content-Type': 'text/html', 'Connection': 'close'}

        except Exception as e:
            print(f"Unexpected Error: {e}")
            gc.collect()
            return "<html><body><h1>Internal Server Error</h1></body></html>", 500, {'Content-Type': 'text/html', 'Connection': 'close'}
    return route

def init_static_file_server(server):
    for file_path in ls('web'):        
        route = file_path[3:]
        print(f"Adding route for {route}")
        server.add_route(route, serve_file(file_path), methods=['GET'])
        if route == "/index.html":
            server.add_route("/", serve_file(file_path), methods=['GET'])