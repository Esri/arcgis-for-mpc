import os
import csv
import requests
import arcpy

tifs = [
    "B01",
    "B02",
    "B03",
    "B04",
    "B05",
    "B06",
    "B07",
    "B08",
    "B8A",
    "B09",
    "B11",
    "B12",
    "AOT",
    "WVP",
    "SCL",
    "visual",
]

template_map = {
    "Aerosol Optical Thickness": tifs[-4:-3],
    "BOA Reflectance": tifs[:-4],
    "BOA Reflectance-10m": tifs[1:4] + tifs[7:8],
    "Multiband": tifs[:-1],
    "SCL-20m": tifs[-2:-1],
    "True Color": tifs[-1:],
    "Water Vapor": tifs[-3:-2],
}

acs_file = r"C:\AMPC_Resources\ACS_Files\esrims_pc_sentinel-2-l2a.acs"

get_asset_file = lambda item, asset_key: os.path.normpath(
    acs_file + item["assets"][asset_key]["href"][57:]
)


def get_row(item, asset_key, apply_template, all_bands):
    row = []
    item_asset = item["assets"][asset_key]
    row.append(get_asset_file(item, asset_key))
    props = item["properties"]
    row.extend(item_asset["proj:bbox"])
    row.extend(item_asset["proj:shape"][::-1])
    row.append(len(item_asset["eo:bands"]) if "eo:bands" in item_asset else 1)
    row.append("U16" if asset_key not in tifs[-2:] else "U8")
    row.append(props["proj:epsg"])
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


def query_stac_api(from_datetime, to_datetime, bbox, props_query, limit):
    query = {}

    query["collections"] = ["sentinel-2-l2a"]

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

    all_templates = list(template_map.keys()) if all_bands else [processing_template]

    rows = [
        get_row(item, asset, apply_template, all_bands)
        for item in stac_items
        for apply_template in all_templates
        for asset in template_map[apply_template]
    ]

    input_data = os.path.abspath("sentinel_table.csv")

    with open(input_data, mode="w", newline="") as table_file:
        csv_writer = csv.writer(table_file)
        csv_writer.writerow(fields)
        csv_writer.writerows(rows)

    raster_type = (
        r"C:\AMPC_Resources\Raster_Types\Table_composite.art.xml"
        if all_bands or len(template_map[processing_template]) > 1
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
    from_datetime = arcpy.GetParameter(1)
    to_datetime = arcpy.GetParameter(2)
    bbox = arcpy.GetParameter(3)
    props_query = arcpy.GetParameter(4)
    limit = arcpy.GetParameter(5)
    processing_template = arcpy.GetParameter(6)

    stac_items = query_stac_api(from_datetime, to_datetime, bbox, props_query, limit)
    project = arcpy.mp.ArcGISProject("CURRENT")
    active_map = project.activeMap
    active_layers = [
        lyr.dataSource for lyr in active_map.listLayers() if hasattr(lyr, "dataSource")
    ]

    add_rasters_to_md(in_mosaic, stac_items, processing_template)
    arcpy.AddMessage(arcpy.GetMessages())

    if not hasattr(in_mosaic, "dataSource") and str(in_mosaic) not in active_layers:
        active_map.addDataFromPath(str(in_mosaic))
        arcpy.AddMessage("Layer added to the map")
