import os
import modal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json
import uuid
import traceback
import logging
from modules.story_generator import generate_short_story
from modules.image_generator import generate_images_description, generate_images
from modules.audio_generation import generate_audio
from modules.video_creator import create_video_with_captions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a Modal App for the video generation API (updated from Stub)
app = modal.App("autoshorts-video-api")

# Create a FastAPI app
web_app = FastAPI()

# Define the request model for video generation
class VideoRequest(BaseModel):
    story: str

# Add CORS middleware to allow requests from any origin
from fastapi.middleware.cors import CORSMiddleware
web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Define the video generation endpoint
@web_app.post("/generate_video")
async def generate_video(req: VideoRequest):
    try:
        logger.info(f"Received request to generate video for story")
        
        # Generate the image descriptions
        logger.info("Generating image descriptions")
        image_descriptions = generate_images_description(req.story)
        
        # Parse the image descriptions
        try:
            data = json.loads(image_descriptions)
            logger.info(f"Generated {len(data['images'])} image descriptions")
        except Exception as e:
            logger.error(f"Error parsing image descriptions: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error parsing image descriptions: {str(e)}")
        
        # Generate audio from the story
        logger.info("Generating audio")
        try:
            audio_file_path = generate_audio(req.story)
            logger.info(f"Generated audio at {audio_file_path}")
        except Exception as e:
            logger.error(f"Error generating audio: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}")
        
        # Generate images based on the descriptions
        logger.info("Generating images")
        try:
            generated_images = generate_images(image_descriptions)
            logger.info(f"Generated {len(generated_images)} images")
        except Exception as e:
            logger.error(f"Error generating images: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error generating images: {str(e)}")
        
        # Create video with the generated images and audio
        logger.info("Creating video with captions")
        try:
            image_files = [img["filename"] for img in generated_images]
            durations = [float(img["time_on_screen"]) for img in generated_images]
            
            # Generate a unique filename for the video
            video_filename = f"output_video_{uuid.uuid4()}.mp4"
            
            # Create the video
            s3_url = create_video_with_captions(
                image_files=image_files,
                durations=durations,
                audio_file=audio_file_path,
                video_filename=video_filename
            )
            
            logger.info(f"Video created successfully, available at: {s3_url}")
            return {"s3_url": s3_url}
        except Exception as e:
            logger.error(f"Error creating video: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(status_code=500, detail=f"Error creating video: {str(e)}")
    
    except Exception as e:
        logger.error(f"Unexpected error in generate_video: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# Create a Modal image with all necessary dependencies
image = (modal.Image.debian_slim()
    .pip_install(
        "fastapi",
        "openai",
        "pydantic",
        "python-multipart",
        "requests",
        "pillow",
        "boto3",
        "moviepy",
        "uuid"
    )
    # Run commands first to set up directories
    .run_commands(
        "mkdir -p /root/modules && touch /root/modules/__init__.py"
    )
    # Then add local files
    .add_local_file("api/modules/story_generator.py", "/root/modules/story_generator.py")
    .add_local_file("api/modules/image_generator.py", "/root/modules/image_generator.py")
    .add_local_file("api/modules/audio_generation.py", "/root/modules/audio_generation.py")
    .add_local_file("api/modules/video_creator.py", "/root/modules/video_creator.py")
)

# Create a Modal FastAPI app that serves the FastAPI app
@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("my-openai-secret"),
        modal.Secret.from_name("my-aws-secret")
    ],
    timeout=600  # 10 minutes timeout for video generation
)
@modal.asgi_app()
def fastapi_app():
    # Setup API keys from environment variables
    os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
    os.environ["AWS_ACCESS_KEY_ID"] = os.environ.get("AWS_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
    
    # Return the FastAPI app
    return web_app

# For local development
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(web_app, host="0.0.0.0", port=8001) 