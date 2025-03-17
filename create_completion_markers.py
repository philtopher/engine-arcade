#!/usr/bin/env python3

import os
import datetime
import glob

BASE_PROJECT_DIR = os.path.expanduser("~/Desktop/gpte-projects")

def create_completion_markers():
    """Create .gpte_done files for any projects that are missing them"""
    project_dirs = [d for d in os.listdir(BASE_PROJECT_DIR) 
                   if os.path.isdir(os.path.join(BASE_PROJECT_DIR, d))]
    
    print(f"Found {len(project_dirs)} projects")
    
    for project_name in project_dirs:
        project_dir = os.path.join(BASE_PROJECT_DIR, project_name)
        done_file = os.path.join(project_dir, ".gpte_done")
        
        # Check if .gpte_done file exists
        if not os.path.exists(done_file):
            # Check if workspace/generated has content
            generated_dir = os.path.join(project_dir, "workspace", "generated")
            if os.path.exists(generated_dir) and os.listdir(generated_dir):
                print(f"Creating completion marker for {project_name}")
                with open(done_file, 'w') as f:
                    f.write(f"Process completed at {datetime.datetime.now()}")
                
                # Copy files to static/project_assets
                project_assets_dir = os.path.join('static', 'project_assets', project_name)
                os.makedirs(project_assets_dir, exist_ok=True)
                
                # Copy files from generated directory
                if os.path.exists(generated_dir):
                    for filename in os.listdir(generated_dir):
                        if filename.endswith(('.html', '.js', '.css')):
                            src_path = os.path.join(generated_dir, filename)
                            dst_path = os.path.join(project_assets_dir, filename)
                            try:
                                with open(src_path, 'r') as src_file:
                                    content = src_file.read()
                                with open(dst_path, 'w') as dst_file:
                                    dst_file.write(content)
                                print(f"  Copied {filename} to {dst_path}")
                            except Exception as e:
                                print(f"  Error copying {filename}: {e}")

if __name__ == "__main__":
    create_completion_markers()
