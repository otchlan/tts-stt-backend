import argparse
import asyncio
import edge_tts
import sys
import os
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define voice mappings with multiple voices for fallback
VOICES = {
    'pl': [
        'pl-PL-MarekNeural', 
        'pl-PL-ZofiaNeural'
    ],
    'en': [
        'en-US-ArthurNeural', 
        'en-US-ChristopherNeural', 
        'en-GB-RyanNeural'
    ]
}

async def text_to_speech_from_file(file_path, language='pl'):
    try:
        # Validate language
        if language not in VOICES:
            logger.error(f"Unsupported language: {language}. Use 'pl' or 'en'.")
            return None
        
        # Read text from the file
        if not os.path.exists(file_path):
            logger.error(f"File {file_path} does not exist.")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read().strip()
        
        # Check if text is not empty
        if not text:
            logger.error(f"The file {file_path} is empty.")
            return None
        
        logger.info(f"Text to synthesize: {text}")
        logger.info(f"Text length: {len(text)} characters")
        
        # Try multiple voices
        for voice in VOICES[language]:
            try:
                logger.info(f"Attempting to synthesize with voice: {voice}")
                
                # Initialize text-to-speech communication
                communicate = edge_tts.Communicate(text=text, voice=voice)
                
                # Generate output filename
                output_filename = f"data/{language}_output.mp3"
                
                # Save the speech synthesis to an MP3 file
                await communicate.save(output_filename)
                
                logger.info(f"Speech synthesis successful using {voice}.")
                logger.info(f"Output saved to {output_filename}")
                return output_filename
            
            except Exception as voice_error:
                logger.error(f"Failed with voice {voice}: {voice_error}")
                # Log additional details about the error
                logger.debug(f"Error details: {sys.exc_info()}")
        
        # If all voices fail
        logger.error("Could not synthesize speech with any available voice.")
        return None
    
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        logger.debug(f"Error details: {sys.exc_info()}")
        return None

def main():
    # Create argument parser
    parser = argparse.ArgumentParser(description='Text-to-Speech converter')
    
    # Add mutually exclusive language group
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-pl', '--polish', action='store_true', help='Use Polish voice')
    group.add_argument('-en', '--english', action='store_true', help='Use English voice')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Determine language
    if args.polish:
        language = 'pl'
    elif args.english:
        language = 'en'
    
    # Define text file path
    text_file = 'data/text.txt'
    
    # Run async function
    try:
        # Use asyncio.run to execute the async function
        result = asyncio.run(text_to_speech_from_file(text_file, language))
        
        if result:
            logger.info(f"TTS conversion complete. File saved: {result}")
        else:
            logger.error("TTS conversion failed.")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        logger.debug(f"Error details: {sys.exc_info()}")
        sys.exit(1)

if __name__ == '__main__':
    main()