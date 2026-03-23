from dotenv import load_dotenv

from app_runtime import ChatAgentApp, create_runtime, run_startup_healthchecks


def main():
    load_dotenv()
    _, runtime = create_runtime()
    run_startup_healthchecks(runtime)
    ChatAgentApp(runtime).run()


if __name__ == "__main__":
    main()
