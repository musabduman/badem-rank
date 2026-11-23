import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from main import app

client = TestClient(app)

@patch("database.baglantiyi_test_et", return_value=True)
def test_saglik_kontrolu(mock_db_test):
    response = client.get("/api/sistem/saglik")
    assert response.status_code == 200
    veri = response.json()
    assert veri["durum"] == "calisiyor"
    assert "supabase" in veri
    assert "model" in veri

@patch("routers.keywords.supabase")
def test_keyword_listesi_bos(mock_supabase):
    # Supabase yanıtını mock'la
    mock_supabase.table().select().order().execute.return_value.data = []
    
    response = client.get("/api/keywords")
    assert response.status_code == 200
    assert response.json() == []

@patch("routers.sistem.supabase")
def test_scrape_loglari_bos(mock_supabase):
    mock_supabase.table().select().order().limit().execute.return_value.data = []
    
    response = client.get("/api/sistem/scrape/loglar?limit=10")
    assert response.status_code == 200
    assert response.json() == []
