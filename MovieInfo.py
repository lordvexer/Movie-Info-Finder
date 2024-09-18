import os
import re
import requests
from tkinter import Tk, filedialog
from googlesearch import search
from mutagen.mp4 import MP4, MP4Tags
from termcolor import colored  


def select_folder():
    root = Tk()
    root.withdraw()
    folder_path = filedialog.askdirectory(title="Select a Folder")
    root.destroy()
    return folder_path

def find_movie_files(folder_path):
    movie_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(('.mp4', '.mkv', '.avi', '.mov')):
                movie_files.append(os.path.join(root, file))
    return movie_files

def extract_search_query(filename):
    base_name = os.path.splitext(filename)[0]
    
    clean_name = re.sub(r'[\.\_\-]', ' ', base_name)
    clean_name = re.sub(r'\b(480p|720p|1080p|HD|Hardsub|WEB-DL|BluRay|HDRip|x264|x265|DVDRip|CAMRip|YTS|RARBG|DigiMoviez|HD1080|Copy)\b', '', clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r'[^A-Za-z0-9\s]', '', clean_name)
    match = re.search(r'([A-Za-z\s]+(?:Part\s*[IVXLCDM0-9]*)?)', clean_name)
    
    if match:
        movie_title = match.group(1).strip()
        return movie_title
    else:
        return re.sub(r'\s+', ' ', clean_name).strip()


def clean_filename(filename):
    filename = os.path.splitext(filename)[0]
    filename = re.sub(r'[\.\_\-]', ' ', filename)
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename

def search_correct_title(query):
    try:
        search_results = search(query, num_results=10)
        return search_results
    except Exception as e:
        print(f"Error searching Google: {e}")
    return []

def fetch_metadata_from_tmdb(filename):
    api_key = '1c178512e84f5a65fcddfc9f3aaaa5ce'
    
    clean_title = extract_search_query(filename)
    
    search_url = f'https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={clean_title}'
    print(f"Request URL: {search_url}")
    
    try:
        response = requests.get(search_url)
        response.raise_for_status()
        data = response.json()
        results = data.get('results', [])
        movie_data = []
        
        for movie in results:
            movie_id = movie.get('id')
            movie_detail = fetch_movie_details_from_tmdb(movie_id, api_key)
            if movie_detail:
                movie_data.append(movie_detail)
        
        return movie_data
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching metadata from TMDb: {e}")
    
    return []


def fetch_movie_details_from_tmdb(movie_id, api_key):
    movie_url = f'https://api.themoviedb.org/3/movie/{movie_id}?api_key={api_key}&append_to_response=credits'
    try:
        response = requests.get(movie_url)
        response.raise_for_status()
        movie = response.json()
        credits = movie.get('credits', {})

        def filter_crew_by_job(crew_list, job_titles):
            job_titles = [job_title.lower() for job_title in job_titles]
            filtered = [f"{member.get('name', 'Unknown')} ({member.get('job', 'Unknown')})"
                        for member in crew_list if any(job_title in member.get('job', '').lower() for job_title in job_titles)]
            return ', '.join(filtered)

        def get_director(crew_list):
            for member in crew_list:
                if member.get('job') == 'Director':
                    return member.get('name', 'Unknown')
            return 'Unknown'

        def get_producers(crew_list):
            producers = [member.get('name', 'Unknown') for member in crew_list if member.get('job') == 'Producer']
            return ', '.join(producers) if producers else 'Unknown'

        def get_composers(crew_list):
            composers = [member.get('name', 'Unknown') for member in crew_list if member.get('job') == 'Composer']
            return ', '.join(composers) if composers else 'Unknown'

        return {
            'title': movie.get('title', 'Unknown'),
            'release_year': movie.get('release_date', 'Unknown')[:4],
            'genre': ', '.join([genre.get('name', 'Unknown') for genre in movie.get('genres', [])]),
            'overview': movie.get('overview', 'Unknown'),
            'director': get_director(credits.get('crew', [])),
            'producer': get_producers(credits.get('crew', [])),
            'writers': filter_crew_by_job(credits.get('crew', []), ['Writer', 'Screenplay']),
            'cast': ', '.join([f"{member.get('name', 'Unknown')} ({member.get('character', 'Unknown')})" for member in credits.get('cast', [])[:5]]),
            'composer': get_composers(credits.get('crew', [])),  
            'rating': movie.get('vote_average', 'Unknown'),
            'release_date': movie.get('release_date', 'Unknown')
        }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching movie details from TMDb: {e}")
    return None


def safe_str(value):
    try:
        return str(value) if value else 'Unknown'
    except Exception:
        return 'Unknown'

def convert_rating_to_stars(rating):
    try:
        rating_5_star = float(rating) / 2  
        return f"{rating_5_star:.1f} / 5" 
    except (ValueError, TypeError):
        return "Unknown"

def update_metadata(movie_file, metadata, file_path):
    try:
        print("\nMetadata to be written:")
        print(f"Title: {safe_str(metadata.get('title', 'Unknown'))}")
        print(f"Release Year: {safe_str(metadata.get('release_year', 'Unknown'))}")
        print(f"Genre: {safe_str(metadata.get('genre', 'Unknown'))}")
        print(f"Description/Overview: {safe_str(metadata.get('overview', 'Unknown'))}")
        print(f"Director: {safe_str(metadata.get('director', 'Unknown'))}")
        print(f"Producer: {safe_str(metadata.get('producer', 'Unknown'))}")
        print(f"Writers: {safe_str(metadata.get('writers', 'Unknown'))}")
        print(f"Cast: {safe_str(metadata.get('cast', 'Unknown'))}")
        print(f"Composer: {safe_str(metadata.get('composer', 'Unknown'))}")
        print(f"Rating: {convert_rating_to_stars(metadata.get('rating', 'Unknown'))}")

        confirm = input("\nDo you want to save this metadata to the file? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Metadata update canceled.")
            return

        movie_file['\xa9nam'] = safe_str(metadata.get('title', 'Unknown'))  # Title
        movie_file['\xa9day'] = safe_str(metadata.get('release_year', 'Unknown'))  # Release Year
        movie_file['\xa9gen'] = safe_str(metadata.get('genre', 'Unknown'))  # Genre
        movie_file['\xa9cmt'] = safe_str(metadata.get('overview', 'Unknown'))  # Description/Overview
        movie_file['\xa9dir'] = safe_str(metadata.get('director', 'Unknown'))  # Director
        movie_file['\xa9pro'] = safe_str(metadata.get('producer', 'Unknown'))  # Producer
        movie_file['\xa9wrt'] = safe_str(metadata.get('writers', 'Unknown'))  # Writers
        movie_file['\xa9ART'] = safe_str(metadata.get('cast', 'Unknown'))  # Cast
        movie_file['\xa9com'] = safe_str(metadata.get('composer', 'Unknown'))  # Composer
        movie_file['\xa9rtng'] = convert_rating_to_stars(metadata.get('rating', 'Unknown'))  # Rating

        movie_file.save()
        print(f"Metadata updated for {file_path}")

        updated_file = MP4(file_path)
        print("Updated Metadata:")
        for tag, value in updated_file.items():
            print(f"{tag}: {value}")

    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
    except PermissionError:
        print(f"Error: Permission denied when accessing the file: {file_path}")
    except Exception as e:
        print(f"Error updating metadata: {e}")



def rename_file(file_path, new_name):
    folder, old_name = os.path.split(file_path)
    extension = os.path.splitext(old_name)[1]
    new_path = os.path.join(folder, new_name + extension)
    
    print(f"Old name: {old_name}")
    print(f"New name: {new_name}{extension}")
    choice = input("Do you want to rename the file to the new format? (y/n): ").strip().lower()
    
    if choice == 'y':
        try:
            os.rename(file_path, new_path)
            print(f"Renamed to {new_path}")
        except Exception as e:
            print(f"Error renaming file: {e}")
    else:
        print("Keeping the old name.")

def choose_movie_from_options(options):
    print("\nMultiple movies found. Please select the correct one:")
    for idx, option in enumerate(options):
        print(f"{idx + 1}. {option.get('title')} ({option.get('release_year', 'Unknown')}) - Rating: {option.get('rating')}")
    
    try:
        choice = int(input("Enter the number of your choice: ")) - 1
        if 0 <= choice < len(options):
            return options[choice]
        else:
            print("Invalid choice. Using the first result.")
            return options[0]
    except ValueError:
        print("Invalid input. Using the first result.")
        return options[0]


def main():
    print("Select a folder containing movie files:")
    folder_path = select_folder()
    
    if not folder_path:
        print("No folder selected. Exiting.")
        return
    
    movie_files = find_movie_files(folder_path)
    
    if not movie_files:
        print("No movie files found in the selected folder.")
        return
    
    results = []

    print(f"Found {len(movie_files)} movie files.\n")
    for file_path in movie_files:
        original_title = clean_filename(os.path.basename(file_path))
        print(f"Original Title: {original_title}")
        
        search_query = extract_search_query(original_title)
        movie_options = fetch_metadata_from_tmdb(search_query)

        if not movie_options:
            print(f"No metadata found for {search_query}.")
            results.append({'original': original_title, 'new': 'N/A', 'status': 'fail'})
            continue
        
        if len(movie_options) == 1:
            selected_movie = movie_options[0]
            print(f"One movie found: {selected_movie['title']} ({selected_movie['release_year']})")
        else:
            selected_movie = choose_movie_from_options(movie_options)
        
        movie_metadata = {
            'title': selected_movie.get('title', 'Unknown'),
            'release_year': selected_movie.get('release_year', 'Unknown'),
            'genre': selected_movie.get('genre', 'Unknown'),
            'overview': selected_movie.get('overview', 'Unknown'),
            'director': selected_movie.get('director', 'Unknown'),
            'writers': selected_movie.get('writers', 'Unknown'),
            'cast': selected_movie.get('cast', 'Unknown'),
            'composer': selected_movie.get('composer', 'Unknown'),
            'rating': selected_movie.get('rating', 'Unknown'),
            'release_date': selected_movie.get('release_date', 'Unknown')
        }

        try:
            movie_file = MP4(file_path)
            update_metadata(movie_file, movie_metadata, file_path)

            new_name = f"{movie_metadata.get('title', 'Unknown')} ({movie_metadata.get('release_year', 'Unknown')})"
            rename_file(file_path, new_name)

            results.append({'original': original_title, 'new': new_name, 'status': 'success'})
        except Exception as e:
            print(f"Error processing {original_title}: {e}")
            results.append({'original': original_title, 'new': 'N/A', 'status': 'fail'})

    print("\nSummary of Processed Movies:\n")
    for result in results:
        status_color = 'green' if result['status'] == 'success' else 'red'
        print(colored(f"Original: {result['original']}", status_color))
        print(colored(f"New: {result['new']}", status_color))
        print(colored(f"Status: {result['status'].capitalize()}\n", status_color))

if __name__ == "__main__":
    main()
