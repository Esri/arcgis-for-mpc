/* Copyright 2023 Esri
 *
 * Licensed under the Apache License Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
 
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
