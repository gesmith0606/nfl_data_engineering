# Test file to demonstrate automated code review system

def complex_function_that_needs_simplification():
    """This function is intentionally complex to trigger the /simplify command"""
    data = []
    for i in range(100):
        if i % 2 == 0:
            if i % 4 == 0:
                if i % 8 == 0:
                    data.append(i * 2)
                else:
                    data.append(i + 1)
            else:
                data.append(i - 1)
        else:
            if i % 3 == 0:
                data.append(i * 3)
            else:
                data.append(i)
    
    # More lines to exceed 50-line threshold
    processed_data = []
    for item in data:
        if item > 50:
            if item > 100:
                if item > 200:
                    processed_data.append(item / 4)
                else:
                    processed_data.append(item / 2)
            else:
                processed_data.append(item + 10)
        else:
            processed_data.append(item * 2)
    
    return processed_data

# This should trigger NFL team validation warning
teams = ["ARI", "ATL", "BAL"]  # Should use NFL_TEAMS from config.py

# This should trigger S3 path warning  
s3_path = "s3://nfl-raw/games/"  # Should use get_s3_path()