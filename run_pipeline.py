import os
import subprocess
import sys

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, "static")
    os.makedirs(static_dir, exist_ok=True)
    
    print("[1/3] Running AI Segmentation (generate_mask.py)...")
    subprocess.run([sys.executable, "generate_mask.py"], check=True, cwd=base_dir)
    
    print("[2/3] Generating synthetic ocean data (make_synthetic_ocean_data.py)...")
    physics_dir = os.path.join(base_dir, "physics_engine")
    subprocess.run([sys.executable, "make_synthetic_ocean_data.py"], check=True, cwd=physics_dir)
    
    print("[3/3] Running Hindcast Engine (hindcast_engine.py)...")
    subprocess.run([sys.executable, "hindcast_engine.py"], check=True, cwd=physics_dir)
    
    print("Pipeline completed successfully!")

if __name__ == "__main__":
    main()
