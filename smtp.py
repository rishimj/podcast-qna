
import smtplib
server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('rishimj@gmail.com', 'your-app-password')
print('SMTP connection successful')
server.quit()
  