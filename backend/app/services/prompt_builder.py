from app.models.backlog import Feature, UserStory, Task


class PromptBuilder:
    def build_task_prompt(
        self,
        task: Task,
        user_story: UserStory,
        feature: Feature,
        repo_context: str = "",
    ) -> str:
        sections = []

        sections.append("# Code Generation Task\n")
        sections.append(f"## Feature: {feature.title}")
        if feature.description:
            sections.append(f"{feature.description}\n")

        sections.append(f"## User Story: {user_story.title}")
        if user_story.description:
            sections.append(f"{user_story.description}")
        if user_story.acceptance_criteria:
            sections.append(f"\n### Acceptance Criteria:\n{user_story.acceptance_criteria}")

        sections.append(f"\n## Task: {task.title}")
        if task.description:
            sections.append(f"{task.description}")

        sections.append("\n## Instructions")
        sections.append(
            "Implement the task described above. Follow these guidelines:\n"
            "- Write clean, well-structured code\n"
            "- Follow existing code conventions in the repository\n"
            "- Create any necessary files and directories\n"
            "- Ensure the code is functional and complete\n"
            "- Do not leave placeholder or TODO comments\n"
        )

        if repo_context:
            sections.append(f"\n## Repository Context\n{repo_context}")

        return "\n".join(sections)

    def build_continuation_prompt(
        self,
        task: Task,
        previous_output: str,
        modified_files: list[str],
    ) -> str:
        sections = []
        sections.append("# Continue Previous Task\n")
        sections.append(f"## Task: {task.title}")
        if task.description:
            sections.append(f"{task.description}")

        sections.append("\n## Previous Progress")
        sections.append("The following files were already modified:")
        for f in modified_files:
            sections.append(f"- {f}")

        if previous_output:
            sections.append(f"\n## Previous Output (summary)\n{previous_output[:2000]}")

        sections.append(
            "\n## Instructions\n"
            "Continue the implementation from where it left off. "
            "The files listed above already have partial changes. "
            "Complete the remaining work for this task."
        )

        return "\n".join(sections)

    def build_verification_prompt(self, task: Task, modified_files: list[str]) -> str:
        return (
            f"Verify that the task '{task.title}' has been fully implemented.\n"
            f"Modified files: {', '.join(modified_files)}\n\n"
            "Check:\n"
            "1. All requirements from the task description are met\n"
            "2. The code compiles/runs without errors\n"
            "3. No placeholder or TODO items remain\n\n"
            "Respond with COMPLETE if the task is done, or INCOMPLETE with details of what's missing."
        )
