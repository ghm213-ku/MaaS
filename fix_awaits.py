import re
import os

files_to_fix = [
    "tests/test_routes_coverage.py",
    "tests/test_coverage_edge_cases.py",
]

funcs = [
    "start_count_rate_measurement",
    "start_count_rate_live_measurement",
    "start_save_raw_tags_measurement",
    "start_correlation_measurement",
    "start_coincidences_measurement",
    "start_startstop_live_measurement",
    "start_histogram_live_measurement",
    "start_correlation_live_measurement",
    "start_set_parameters",
    "list_all_channels",
    "list_available_channels",
    "book_channels",
    "release_channels",
    "get_user_name_channels",
    "stop_measurement",
    "get_measurement_status",
    "list_measurements",
    "log_measurement_request",
    "log_measurement_response",
    "log_measurement_error"
]

pattern = re.compile(r'await\s+(' + '|'.join(funcs) + r')\(')

for file in files_to_fix:
    with open(file, "r") as f:
        content = f.read()
    
    new_content = pattern.sub(r'\1(', content)
    
    with open(file, "w") as f:
        f.write(new_content)

print("Fixed awaits.")
