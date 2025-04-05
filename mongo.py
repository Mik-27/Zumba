import urllib
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime
import os

password = os.environ.get("MONGO_PWD")

uri = f"mongodb+srv://admin:Admin1234@zoomcluster.9kalesj.mongodb.net/?retryWrites=true&w=majority&appName=ZoomCluster"
# uri = "mongodb+srv://admin:@zoomcluster.9kalesj.mongodb.net/?appName=ZoomCluster"
# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi('1'))
# Create a new client and connect to the server
client = MongoClient(uri)
db = client["ZoomBA"]
collection = db["leaderboards"]

# Function to insert meeting data
def insert_meeting_data(meeting_id, start_time, duration):
    meeting_data = {
        "meeting_id": meeting_id,
        "start_time": start_time,
        "duration": duration,
        "participants":[]
    }

    # Insert data into MongoDB
    collection.insert_one(meeting_data)
    print(f"Data for meeting {meeting_id} inserted successfully!")


def update_participant_field(meeting_id, user_id, field_name, new_value):
    # Query to find the participant by user_id in the meeting
    query = {
        "meeting_id": meeting_id,
        "participants.user_id": user_id
    }

    # Dynamically create the update operation using the field_name
    update = {
        "$set": {
            # Update the specified field
            f"participants.$.{field_name}": new_value
        },
        "$setOnInsert": {
            # Add the field with the default value if it doesn't exist
            f"participants.$.{field_name}": new_value
        }
    }

    # Perform the update
    result = collection.update_one(query, update, upsert=False)  # No upsert for existing documents, only add the field if missing

    if result.matched_count > 0:
        print(f"Updated {field_name} for user {user_id} in meeting {meeting_id}")
    else:
        print(f"User {user_id} not found in meeting {meeting_id}")

# Function to get participant data
def get_participant_data(meeting_id, user_id):
    query = {
        "meeting_id": meeting_id,
        "participants.user_id": user_id
    }
    meeting_data = collection.find_one(query)
    if meeting_data:
        participant_data = next(
            (participant for participant in meeting_data["participants"] if participant["user_id"] == user_id), None)
        return participant_data
    else:
        print(f"No data found for user {user_id} in meeting {meeting_id}")
        return None
    
# Function to increment fields for a participant
def increment_participant_field(meeting_id, user_id, field_name, increment_value=1):
    # Query to find the participant by user_id in the meeting
    query = {
        "meeting_id": meeting_id,
        "participants.user_id": user_id
    }
    # Dynamically create the update operation using the field_name and increment_value
    update = {
        "$inc": {
            # Increment the specified field by increment_value
            f"participants.$.{field_name}": increment_value
        },
        "$setOnInsert": {
            # Initialize the field to 0 if it doesn't exist
            f"participants.$.{field_name}": 1
        }
    }
    # Perform the update
    result = collection.update_one(query, update)

    if result.matched_count > 0:
        print(
            f"Incremented {field_name} for user {user_id} in meeting {meeting_id} by {increment_value}")
    else:
        print(f"User {user_id} not found in meeting {meeting_id}")

# Function to add a participant
def add_presence_entry(meeting_id, user_id, user_name, join_time):
    # Check if the participant already exists in the meeting document
    query = {
        "meeting_id": meeting_id,
        "participants.user_id": user_id
    }
    # Check if the participant exists in the meeting
    participant_exists = collection.find_one(query)
    if participant_exists:
        # If the participant exists, just push the join time into the "presence" array
        update = {
            "$push": {
                "participants.$.presence": {
                    "joined": join_time,
                    "left": None  # Initially, "left" will be None
                }
            }
        }
        # Perform the update to add the join time to the participant's presence array
        result = collection.update_one(query, update)
        if result.matched_count > 0:
            print(f"User {user_id} joined the meeting at {join_time}")
        else:
            print(
                f"Error adding presence for user {user_id} in meeting {meeting_id}")
    else:
        # If the participant does not exist, we need to create a new participant entry and then add the presence
        new_participants = {
            "user_id": user_id,
            "user_name": user_name,
            "presence": [
                {
                    "joined": join_time,
                    "left": None  # Initially, "left" will be None
                }
            ]
        }
        update = {
            "$push": {
                "participants": new_participants  # Add the new participant to the participants array
            }
        }
        # Perform the update to add the new participant and their presence
        result = collection.update_one({"meeting_id": meeting_id}, update)
        if result.matched_count > 0:
            print(f"New user {user_id} joined the meeting at {join_time}")
        else:
            print(f"Error adding new user {user_id} to meeting {meeting_id}")

# Function to update the "left" time for a participant
def add_leave_time(meeting_id, user_id, leave_time):
    # Query to find the document with the meeting_id and user_id
    query = {
        "meeting_id": meeting_id,
        "participants.user_id": user_id,
        # Ensure we update the entry where "left" is None
        "participants.presence.left": None
    }
    # Update operation to set the "left" time
    update = {
        "$set": {
            # Update the "left" field for the correct entry
            "participants.$.presence.$[elem].left": leave_time
        }
    }
    # Array filter to only update the correct "presence" entry (where "left" is None)
    array_filter = [{"elem.left": None}]
    # Perform the update
    result = collection.update_one(query, update, array_filters=array_filter)

    if result.matched_count > 0:
        print(f"User {user_id} left the meeting at {leave_time}")
    else:
        print(
            f"User {user_id} not found in meeting {meeting_id} or they have already left.")

# Function to calculate total duration of a participant in the meeting
def calculate_total_duration(meeting_id):
    # Get the meeting document for the given meeting_id
    meeting = collection.find_one({"meeting_id": meeting_id})
    if not meeting:
        print(f"Meeting {meeting_id} not found.")
        return
    # Current time to consider for any "None" left times
    current_time = datetime.now()
    result = {}
    # Iterate over each student in the meeting
    for participant in meeting["participants"]:
        total_duration = 0  # Initialize total duration for the student
        # Calculate the duration for each presence entry
        for presence_entry in participant["presence"]:
            joined_time = presence_entry["joined"]
            left_time = presence_entry["left"]
            # If left_time is None, use current time for calculation
            if left_time is None:
                left_time = current_time
            # Ensure that both times are datetime objects
            if isinstance(joined_time, str):
                joined_time = datetime.fromisoformat(joined_time)
            if isinstance(left_time, str):
                left_time = datetime.fromisoformat(left_time)
            # Calculate the duration for this presence entry
            duration = (left_time - joined_time).total_seconds()  # in seconds
            total_duration += duration
        total_duration_minutes = round(total_duration / 60, 2)
        result[participant["user_id"]] = total_duration_minutes
    return result

def get_duration_by_meeting_id(meeting_id):
    # Query to find the document by meeting_id
    query = {"meeting_id": meeting_id}
    
    # Fetch the document based on the query
    document = collection.find_one(query)
    
    if document:
        # Retrieve the "duration" field
        duration = document.get("duration")
        print(f"Duration for meeting_id {meeting_id}: {duration}")
        return duration
    else:
        print(f"No document found for meeting_id {meeting_id}")
        return None

def get_engagement_score(meeting_id, user_id):
    # Query to find the document for the given meeting_id and participant's user_id
    query = {
        "meeting_id": meeting_id,
        "participants.user_id": user_id
    }
    
    # Fetch the document based on the query
    document = collection.find_one(query)
    
    if document:
        # Loop through participants to find the matching user_id
        for participant in document.get("participants", []):
            if participant["user_id"] == user_id:
                # Retrieve the engagement score for the participant
                engagement_score = participant.get("engagement_score")
                
                if engagement_score is not None:
                    print(f"Engagement score for user {user_id} in meeting {meeting_id}: {engagement_score}")
                    return engagement_score
                else:
                    print(f"Engagement score not found for user {user_id} in meeting {meeting_id}")
                    return None
    else:
        print(f"No meeting found with meeting_id {meeting_id}")
        return None
    
def calculate_final_score(scores_dict):
    final_scores = {}
    
    for user, scores in scores_dict.items():
        # Extract attendance score and engagement score
        att_scr = scores.get("att_scr")
        eng_scr = scores.get("eng_scr")
        
        # Ensure the engagement score is an integer (if it's a string)
        if isinstance(eng_scr, str):
            eng_scr = int(eng_scr)
        
        # Calculate the final score with 70% weightage to attendance and 30% weightage to engagement
        final_score = (att_scr * 0.7) + (eng_scr * 0.3)
        
        # Store the final score in the dictionary
        final_scores[user] = round(final_score, 2)  # Rounding to 2 decimal places
    
    return final_scores
   
def add_final_score(meeting_id):
    participant_durations = calculate_total_duration(meeting_id)
    meeting_duration = get_duration_by_meeting_id(meeting_id=meeting_id)
    for user_id in participant_durations.keys():
        user_duration = participant_durations[user_id]
        update_participant_field(meeting_id=meeting_id, user_id=user_id, field_name="time_attended", new_value=user_duration)

        att_score = round((user_duration / meeting_duration) * 10,2)
        eng_score = get_engagement_score(meeting_id=meeting_id, user_id=user_id)
        final_score = (att_score * 0.7) + (eng_score * 0.3)
        update_participant_field(meeting_id=meeting_id, user_id=user_id, field_name="final_scores", new_value=final_score)

