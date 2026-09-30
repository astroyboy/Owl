from .auth import Settings, SungrowAuthenticator

if __name__ == "__main__":
    print(SungrowAuthenticator(Settings.from_env()).login())
