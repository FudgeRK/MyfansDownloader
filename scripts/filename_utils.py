import os
import string
from threading import Lock

filename_lock = Lock()
generated_filenames = set()

def read_filename_config(config):
    filename_config = {
        'pattern': config.get('Filename', 'pattern', fallback='{id}'),
        'separator': config.get('Filename', 'separator', fallback='_'),
        'numbers': config.get('Filename', 'numbers', fallback='1'),
        'letters': config.get('Filename', 'letters', fallback='A').upper()
    }
    return filename_config

def validate_filename_config(filename_config):
    allowed_placeholders = {'{number}', '{date}', '{letter}', '{creator}', '{id}'}
    pattern_placeholders = set(part for part in filename_config['pattern'].split('_') if part.startswith('{') and part.endswith('}'))
    if not pattern_placeholders.intersection(allowed_placeholders):
        print("Warning: The filename pattern does not contain any valid placeholders. Using post ID as filename.")
        return False
    return True

def generate_filename(post, filename_config, output_folder):
    pattern = filename_config['pattern']
    separator = filename_config['separator']

    if '{number}' in pattern:
        numbers_str = filename_config['numbers']
        pattern = pattern.replace('{number}', numbers_str)
    
    if '{date}' in pattern:
        published_at = post.get("published_at")
        if published_at:
            date_str = published_at.split('T')[0]
            pattern = pattern.replace('{date}', date_str)
        else:
            pattern = pattern.replace('{date}', 'unknown_date')
        
    if '{letter}' in pattern:
        letters_str = filename_config['letters']
        pattern = pattern.replace('{letter}', letters_str)
        
    if '{creator}' in pattern:
        creator_name = post['user']['username']
        pattern = pattern.replace('{creator}', creator_name)
        
    if '{id}' in pattern:
        post_id = post.get("id", 'unknown_id')
        pattern = pattern.replace('{id}', str(post_id))
        
    base_filename = pattern

    if not base_filename.lower().endswith('.mp4'):
        base_filename += '.mp4'

    filename = base_filename
    counter = 1
    base_name_without_ext, ext = os.path.splitext(base_filename)
    
    global filename_lock
    global generated_filenames
    with filename_lock:
        while filename in generated_filenames or os.path.exists(os.path.join(output_folder, filename)):
            filename = f"{base_name_without_ext}_{counter}{ext}"
            counter += 1
        generated_filenames.add(filename)

    return filename
