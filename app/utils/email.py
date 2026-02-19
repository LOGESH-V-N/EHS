import smtplib

# -----------------------------
# Helper: Send email (SMTP)
# -----------------------------
def send_email(to_email, otp):
    from_email = "thariqahamedks@gmail.com"
    password = "ychfphiknnskcqpg"

    subject = "Your OTP for Password Reset"
    body = f"Your OTP is: {otp}. It is valid for 10 minutes."

    message = f"Subject: {subject}\n\n{body}"

    try:
        print("abssolute")
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(from_email, password)
        server.sendmail(from_email, to_email, message)
        server.quit()
        return True
    except Exception as e:
        print("Email error:", e)
        return False

