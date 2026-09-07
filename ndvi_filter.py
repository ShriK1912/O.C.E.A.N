import pystac_client
import planetary_computer
import rasterio
import rasterio.windows
import numpy as np

def fetch_and_process_marine_images():
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    # Centered deep marine box
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=[-90.0, 26.5, -89.0, 27.5],  
        datetime="2026-03-01/2026-03-31",
        query={"eo:cloud_cover": {"lt": 5}},
    )

    items = list(search.get_items())
    if not items:
        print("No matching marine satellite images found.")
        return

    selected_item = items[0]
    print(f"Selected Deep Ocean Scene ID: {selected_item.id}")

    # 1. Process and Save Trimmed True Color Ocean Image (RGB)
    visual_url = selected_item.assets["visual"].href
    with rasterio.open(visual_url) as src:
        # Read all bands and find valid data window (non-black pixels)
        data = src.read()
        # Create mask of valid pixels (where any RGB band has data)
        valid_mask = np.any(data > 0, axis=0)
        rows, cols = np.where(valid_mask)
        
        if len(rows) > 0 and len(cols) > 0:
            ymin, ymax = rows.min(), rows.max()
            xmin, xmax = cols.min(), cols.max()
            window = rasterio.windows.Window(xmin, ymin, xmax - xmin, ymax - ymin)
            
            # Read cropped data and update profile
            trimmed_data = src.read(window=window)
            profile = src.profile
            transform = rasterio.windows.transform(window, src.transform)
            profile.update(height=window.height, width=window.width, transform=transform)
        else:
            trimmed_data = data
            profile = src.profile

    with rasterio.open("true_color_ocean.tif", "w", **profile) as dst:
        dst.write(trimmed_data)
    print("Saved clean trimmed ocean image as: true_color_ocean.tif")

    # 2. Compute and Save Trimmed Marine NDVI Oil Mask
    band4_url = selected_item.assets["B04"].href
    band8_url = selected_item.assets["B08"].href

    with rasterio.open(band4_url) as red:
        r = red.read(1, window=window).astype(np.float32)
        mask_profile = red.profile

    with rasterio.open(band8_url) as nir:
        n = nir.read(1, window=window).astype(np.float32)

    np.seterr(divide='ignore', invalid='ignore')
    ndvi = (n - r) / (n + r)
    
    mask_potential_oil = (ndvi < -0.05) & (ndvi > -0.18)

    mask_profile.update(
        height=window.height,
        width=window.width,
        transform=transform,
        dtype=rasterio.uint8,
        count=1,
        compress='deflate'
    )

    with rasterio.open("oil_slick_filtered_mask.tif", "w", **mask_profile) as dst:
        dst.write(mask_potential_oil.astype(np.uint8) * 255, 1)

    print("Saved clean trimmed ocean anomaly mask as: oil_slick_filtered_mask.tif")

if __name__ == "__main__":
    fetch_and_process_marine_images()