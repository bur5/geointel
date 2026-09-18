import os
os.environ["DATABASE_URL"]="sqlite://"
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from geointel.api.app import app
from geointel.domain.database import get_session
from geointel.domain.models import Base
@pytest.fixture
def session():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine); factory=sessionmaker(bind=engine,expire_on_commit=False)
    with factory() as value: yield value
    Base.metadata.drop_all(engine)
@pytest.fixture
def client(session):
    app.dependency_overrides[get_session]=lambda: session
    with TestClient(app) as value: yield value
    app.dependency_overrides.clear()
