# AI StorySprint Editing

A working full-stack course platform built with Python's standard library and SQLite. It includes real database-backed authentication, role authorization, persistent progress, secure/private media endpoints, editable lessons/resources, and admin student management.

## Access

The hosted preview starts on port 8000.

### Administrator
- Email: `admin@storysprint.local`
- Password: `Admin123!`

### Demo student
- Email: `student@storysprint.local`
- Password: `Student123!`

Change passwords after first login. New public enrollments begin as **Pending** and an administrator activates them.

## Simple administrator guide

1. Open the website URL and choose **Login**.
2. Log in with the administrator details above; this opens the separate admin dashboard.
3. To add a student, open **Students**, fill in “Add student,” choose Active or Pending, and press **Add**.
4. To edit a lesson, open **Lessons**, choose **Edit lesson**, change the fields, and save.
5. To attach a video, open that lesson, find **Video**, choose a private upload or secure external URL, and save. Student playback always passes through an authorization check.
6. To add a document, open **Resources** → **Add resource**, select Document, choose a file, and save.
7. To add a link, choose Link, enter its title and URL, and save.
8. To add text, choose Text, enter the title and content, and save.
9. To view progress, open **Students** and select **View** beside a student.
10. Share the generated Arena preview URL. Students select **Enroll Now**; approve them in **Students** by setting course access to Active.

## Storage and security

- Database: `storysprint.db`
- Private uploads: `uploads/`
- Passwords: salted PBKDF2 hashes; never visible to administrators
- Sessions: random database-backed, HTTP-only cookies lasting 30 days
- Forms: CSRF protected
- Videos/documents: authorization checked before protected delivery
- External video sources: proxied server-side rather than placed in lesson HTML

No payment gateway is included. The `course_access` model (`pending`, `active`, `suspended`) is ready for a future payment integration. The course model supports more courses/modules/lessons in the future.
Deployment configured for Vercel.
