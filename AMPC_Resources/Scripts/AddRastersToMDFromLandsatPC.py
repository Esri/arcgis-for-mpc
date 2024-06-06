"""
Copyright 2023 Esri

Licensed under the Apache License Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import json
import csv
import requests
import arcpy

sr_tifs = [
    "coastal",
    "blue",
    "green",
    "red",
    "nir08",
    "swir16",
    "swir22",
]

qa_band = "qa_pixel"
sr_cloud_band = "cloud_qa"
level1_nir2_band = "nir09"

pixel_type_map = {"uint16": "U16", "uint8": "U8"}

acs_file = r"C:\AMPC_Resources\ACS_Files\esrims_pc_landsat-c2-l2.acs"

get_asset_file = lambda item, asset_key: os.path.normpath(
    acs_file + item["assets"][asset_key]["href"][54:]
)


def get_row(item, asset_key, apply_template, all_bands):
    row = []
    item_asset = item["assets"][asset_key]
    row.append(get_asset_file(item, asset_key))
    props = item["properties"]
    row.extend(item["bbox"])
    row.extend(props["proj:shape"][::-1])
    row.append(len(item_asset["eo:bands"]) if "eo:bands" in item_asset else 1)
    row.append(pixel_type_map[item_asset["raster:bands"][0]["data_type"]])
    row.append(4326)
    row.append(f"{item['id']}-{asset_key}")
    row.append(props["datetime"])
    row.append(apply_template)
    product_name = f"{item['id']}_{apply_template}" if all_bands else item["id"]
    row.append(product_name)
    return row


def get_items(query, get_all_items):
    url = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    all_items = []
    more_items = True
    while more_items:
        data = requests.post(url, json=query)

        if data.status_code != 200 or data.headers.get("content-type") not in [
            "application/json",
            "application/geo+json",
            "application/json;charset=utf-8",
        ]:
            raise RuntimeError(
                f"Invalid Response: Please verify that the specified query is correct-\n{data.text}"
            )

        json_data = data.json()
        if "type" not in json_data or json_data["type"] != "FeatureCollection":
            raise RuntimeError(
                f"Invalid JSON Response from the STAC API: Please verify that the specified query is correct-\n{json_data}"
            )

        json_data = data.json()
        items = json_data["features"]
        if not get_all_items:
            return items
        all_items.extend(items)
        next_request = json_data["links"][0]
        if next_request["rel"] == "next":
            url = next_request["href"]
            query = next_request["body"]
        else:
            more_items = False

    return all_items


def query_stac_api(collection, from_datetime, to_datetime, bbox, props_query, limit):
    query = {}

    collection_map = {
        "Landsat Collection 2 Level-1": "landsat-c2-l1",
        "Landsat Collection 2 Level-2": "landsat-c2-l2",
    }

    collection_id = collection_map[collection]
    query["collections"] = [collection_id]

    datetime = (
        from_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        if from_datetime is not None
        else from_datetime
    )
    to_datetime = (
        to_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        if to_datetime is not None
        else to_datetime
    )

    datetime = (
        datetime + f"/{to_datetime}"
        if datetime is not None and to_datetime is not None
        else datetime
    )

    if datetime is not None:
        query["datetime"] = datetime

    query_filter = {}

    operators = {
        "lessthan": "lt",
        "lessthanequals": "lte",
        "greaterthan": "gt",
        "greaterthanequals": "gte",
        "equals": "eq",
        "notequals": "neq",
    }

    for i in range(props_query.rowCount):
        row = [index[1:-1] for index in props_query.getRow(i).split(" ")]
        field = "eo:cloud_cover" if row[0].lower() == "cloudcover" else row[0]
        op = operators[row[1].lower()] if row[1].lower() in operators else row[1]
        val = row[2]
        try:
            decoded_val = json.loads(val)
            if isinstance(decoded_val, list):
                val = decoded_val
        except json.JSONDecodeError:
            pass
        op_val = {op: val}
        row_filter = {field: op_val}
        if field in query_filter:
            query_filter[field].update(op_val)
        else:
            query_filter.update(row_filter)

    if query_filter:
        query["query"] = query_filter

    if isinstance(bbox, arcpy.Extent):
        projected_extent = None
        original_sr = bbox.spatialReference
        projection_sr = arcpy.SpatialReference(4326)
        if original_sr is None or not original_sr.name:
            raise RuntimeError(
                "Invalid bbox: Extent object should contain spatialReference"
            )
        try:
            projected_extent = (
                bbox.projectAs(projection_sr) if original_sr != projection_sr else bbox
            )
        except Exception:
            raise RuntimeError(
                "Unsupported bbox: project operation failed for the given Polygon/Extent object"
            )
        bbox_list = [
            projected_extent.XMin,
            projected_extent.YMin,
            projected_extent.XMax,
            projected_extent.YMax,
        ]
        query["bbox"] = bbox_list

    get_all_items = False

    if limit > 0:
        query["limit"] = limit
    else:
        query["limit"] = 1000
        get_all_items = True

    items = get_items(query, get_all_items)

    arcpy.AddMessage(f"No. of STAC items queried: {len(items)}")

    if len(items) < 1:
        raise RuntimeError("No STAC items found. Please specify a better query")

    return items


def add_rasters_to_md(in_mosaic, stac_items, processing_template):
    fields = [
        "Raster",
        "xMin",
        "yMin",
        "xMax",
        "yMax",
        "nRows",
        "nCols",
        "nBands",
        "PixelType",
        "SRS",
        "Name",
        "AcquisitionDate",
        "ProductName",
        "GroupName",
    ]

    all_bands = True if processing_template.upper() == "ALL BANDS" else False
    rows = []
    for item in stac_items:
        props = item["properties"]

        level_2_product = item["collection"] == "landsat-c2-l2"
        oli_tirs = True if props["platform"] in ["landsat-8", "landsat-9"] else False
        st_product = True if props["landsat:correction"] == "L2SP" else False

        sr_bands = (
            sr_tifs
            if oli_tirs
            else sr_tifs[1:] if level_2_product else sr_tifs[2:5] + [level1_nir2_band]
        )
        st_band = "lwir11" if oli_tirs else "lwir"

        mb_bands = sr_bands + ([st_band, qa_band] if st_product else [qa_band])

        if level_2_product and not oli_tirs:
            mb_bands.append(sr_cloud_band)

        template_map = {
            "Multiband": mb_bands,
            "QA": [qa_band],
        }

        if st_product:
            template_map["Surface Temperature"] = [st_band]
            template_map["Surface Reflectance"] = sr_bands
        else:
            template_map["Multispectral"] = sr_bands

        all_templates = (
            list(template_map.keys()) if all_bands else [processing_template]
        )

        for apply_template in all_templates:
            asset_keys = template_map.get(apply_template)

            if not asset_keys:
                arcpy.AddWarning(
                    f"{apply_template} template is not supported for Item: {item['id']}"
                )

                continue

            for asset in asset_keys:
                row = get_row(item, asset, apply_template, all_bands)
                rows.append(row)

    input_data = os.path.abspath("landsat_table.csv")

    with open(input_data, mode="w", newline="") as table_file:
        csv_writer = csv.writer(table_file)
        csv_writer.writerow(fields)
        csv_writer.writerows(rows)

    raster_type = (
        r"C:\AMPC_Resources\Raster_Types\Table_composite.art.xml"
        if all_bands or processing_template not in ["QA", "Surface Temperature"]
        else "Table / Raster Catalog"
    )

    arcpy.management.AddRastersToMosaicDataset(
        in_mosaic_dataset=in_mosaic,
        raster_type=raster_type,
        input_path=input_data,
    )

    try:
        os.remove(input_data)
    except Exception as e:
        arcpy.AddWarning(f"{input_data} may not have been deleted: {e}")


if __name__ == "__main__":
    in_mosaic = arcpy.GetParameter(0)
    collection = arcpy.GetParameterAsText(1)
    from_datetime = arcpy.GetParameter(2)
    to_datetime = arcpy.GetParameter(3)
    bbox = arcpy.GetParameter(4)
    props_query = arcpy.GetParameter(5)
    limit = arcpy.GetParameter(6)
    processing_template = arcpy.GetParameter(7)

    stac_items = query_stac_api(
        collection, from_datetime, to_datetime, bbox, props_query, limit
    )
    project = arcpy.mp.ArcGISProject("CURRENT")
    active_map = project.activeMap
    active_layers = [
        lyr.dataSource for lyr in active_map.listLayers() if hasattr(lyr, "dataSource")
    ]

    add_rasters_to_md(in_mosaic, stac_items, processing_template)
    arcpy.AddMessage(arcpy.GetMessages())

    if not hasattr(in_mosaic, "dataSource") and str(in_mosaic) not in active_layers:
        active_map.addDataFromPath(str(in_mosaic))
        arcpy.AddMessage(f"Layer added to the map")
