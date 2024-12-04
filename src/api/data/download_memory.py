def download_memory(request):
    print("WIFI: Download memory values file")
    gc.collect()    
    try:
        # Stream memory values directly to the response to save RAM
        def memory_values_generator():
            for value in ram_access:
                yield f"{value}\n".encode('utf-8')               

        headers = {
            'Content-Type': 'text/plain',
            'Content-Disposition': 'attachment; filename=memory.txt',
            'Connection': 'close'
        }
        
        return memory_values_generator(), 200, headers
    
    except Exception as e:
        print(f"Error preparing memory values: {str(e)}")
        gc.collect()
        return 500, {"error": str(e)}
