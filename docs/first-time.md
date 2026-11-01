---
title: Only used AI on your phone? Start here
description: The folder, the assistant, permission and the saved notes, in the order you meet them.
---

Used ChatGPT or Gemini on a phone? You already know how to ask for help in plain words. On a computer, with a project folder, the same words do more: the assistant can read and change real files. project-manager gives it a notebook to write in, so the next chat starts where you stopped.

## The folder

A project is a folder on your computer, for example `C:\projects\my-site` or `~/projects/my-site`. Everything below happens inside it: your code, and the notes project-manager adds. You open that folder in your assistant, and it starts there. Notes in one folder are not in another.

## The assistant

The assistant is an AI program that can also use the folder: Claude Code, Codex, Pi or another. You type in ordinary words, as on your phone; when it is allowed to, it edits files and runs checks. It is not a website you visit: it runs on your computer, and the service behind it may charge for what it processes.

## Permission

The assistant can change your files, so it has to ask. Say what you want, then read what it plans to change; "yes" is a decision, and so is "no". This setup asks before changing your files; your assistant's own permission settings matter too. The AI can make mistakes; check what it did.

## Saved notes

The assistant forgets most of a chat when it closes. project-manager keeps the work in files instead: the job list, the reason for a choice and where you stopped, in `.pm/` inside your project. Think of that folder as the project's notebook. It is not the AI's memory and it does not keep every word of a chat: in a new chat, the assistant reads the notes and checks the files again.

![Four panels: you ask for a small change; the assistant shows its plan, you approve, it changes the file and runs the check; the notes are saved in .pm/ in your project; next time a new chat reads the notes, checks the files and names the next step.](../public/next-chat.svg)

*The new chat reads saved files, not the old assistant's mind.*

## Next

You need a computer, a project folder and an assistant that can edit files. [Install with your agent](install-with-agent.md): paste one prompt, answer a few questions, then type `/pm-setup`.
