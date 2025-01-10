# task_processor.py
''' 
To kod dla asystenta zarządzania jest
'''

def parse_project_tasks_from_transcription(transcribed_text: str):
    """
    Parses out tasks from the transcribed text.
    
    - A project is indicated by a word that starts with '#'.
    - We capture everything after that hashtag until we see:
      - The next hashtag (#something),
      - Or an end word: 'finish' or 'koniec'.
    - That captured text is a single "task" under that project.

    Returns a list of dicts, each containing:
      {
        "project": <project_name_without_#>,
        "task_text": <collected text until end-of-task>
      }
    """

    words = transcribed_text.strip().split()

    tasks = []
    current_project = None
    current_task_words = []

    for word in words:
        lowered = word.lower()

        if lowered.startswith('#'):
            # if we were already building a task, finalize it
            if current_project and current_task_words:
                tasks.append({
                    "project": current_project,
                    "task_text": " ".join(current_task_words)
                })

            # start a new project
            current_project = word[1:]  # remove the '#'
            current_task_words = []

        elif lowered in ('finish', 'koniec'):
            # end the current project's task
            if current_project and current_task_words:
                tasks.append({
                    "project": current_project,
                    "task_text": " ".join(current_task_words)
                })
            # reset
            current_project = None
            current_task_words = []

        else:
            # if we're inside a project context, accumulate words for the task
            if current_project is not None:
                current_task_words.append(word)

    # If we ended without saying "finish"/"koniec", optionally finalize the last project
    if current_project and current_task_words:
        tasks.append({
            "project": current_project,
            "task_text": " ".join(current_task_words)
        })

    return tasks