from naryad.prompt import build_system_prompt


def test_clients_in_prompt(clients):
    prompt = build_system_prompt(clients)
    assert "Дента-Люкс: Иванов С.С., Соколова Н.А." in prompt
    assert "крестом" in prompt
