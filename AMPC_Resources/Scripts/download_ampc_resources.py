"""
Download additional AMPC resources such as notebooks and script tools from GitHub repository
https://github.com/ArcGIS/arcgis-for-mpc
"""
import arcpy
import requests, zipfile, io, shutil
url = 'https://github.com/Esri/raster-functions/archive/master.zip'
def download_ampc_resources(output_folder):
    """Script code goes below"""
    r = requests.get(url)
    
    if r.status_code == 200:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        z.extractall(output_folder)
    else:
        raise RuntimeError("Repository not found")
    
    return
if __name__ == "__main__":
    output_folder = arcpy.GetParameterAsText(0)
    download_ampc_resources(output_folder)
