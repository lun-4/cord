import cord.tui

def main():
    email = input('Email: ')
    password = input('Password: ')

    tui_client = cord.tui.TUIClient(email=email, password=password)
    tui_client.start()

if __name__ == '__main__':
    main()
