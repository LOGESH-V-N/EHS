import smtplib
import os

# -----------------------------
# Helper: Send email (SMTP)
# -----------------------------
def send_email(to_email, otp):
    from_email = os.getenv("Email")
    password = os.getenv("Password")
    server = os.getenv("Server")
    subject = "Your OTP for Password Reset"
    body = f"Your OTP is: {otp}. It is valid for 10 minutes."

    message = f"Subject: {subject}\n\n{body}"

    try:
        print("abssolute")
        server = smtplib.SMTP(server, 587)
        server.starttls()
        server.login(from_email, password)
        server.sendmail(from_email, to_email, message)
        server.quit()
        return True
    except Exception as e:
        print("Email error:", e)
        return False

