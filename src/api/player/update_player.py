    def app_updatePlayer(request):                     
        try:    
            body = request.data                   
            initials = body['initials'].upper()[:3]
            name = body['full_name'][:16]
            index = int(body['index'])  
            if index < 0 or index > DataStore.memory_map["names"]["count"]:
                return "Invalid index"    
                    
            DataStore.write_record("names",{"initials":initials,"full_name":name},index-1)                    
            return "Update successful"
        except Exception as e:
            return f"An error occurred: {e}"