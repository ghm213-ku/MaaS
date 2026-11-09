import os
from datetime import datetime

def format_target_location(target_location: str, measurement_type: str) -> str:
    """Format the target location, replacing placeholders and ensuring it's a file path."""
    if not target_location:
        return target_location
        
    dt_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    formatted = target_location.replace("{datetime}", dt_str)
    formatted = formatted.replace("{measurement-type}", measurement_type)
    # "~/Desktop/..." resolves to the worker user's home, not the worker's cwd
    formatted = os.path.expanduser(formatted)

    # If the path represents an existing directory or ends with a slash, append a default filename
    if os.path.isdir(formatted) or formatted.endswith(('/', '\\')):
        # TimeTagger's FileWriter writes .ttbin files (it appends .ttbin itself
        # if the name lacks it), so name raw-tag files .ttbin up front.
        ext = ".ttbin" if measurement_type == "save_raw_tags" else ".csv"
        formatted = os.path.join(formatted, f"{measurement_type}_{dt_str}{ext}")
        
    return formatted
