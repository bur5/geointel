from geointel.domain.models import AnalysisRun, Forecast
QUESTION="Analyze the risk of organized political violence in Spain over the next 12 months, separated by conflict type."
def test_health(client): assert client.get("/health").json()["status"]=="ok"
def test_request_validation(client): assert client.post("/analysis",json={"location":"S","question":"short","horizon_months":0}).status_code==422
def test_spain_pipeline_persistence_retrieval_and_red_team(client,session):
    response=client.post("/analysis",json={"location":"Spain","question":QUESTION,"horizon_months":12})
    assert response.status_code==201
    data=response.json(); assert data["status"]=="completed" and len(data["forecast_ids"])==4
    assert data["red_team_output"]["false_positive_risks"]
    assert data["synthesis_output"]["incorporated_critiques"]
    assert session.query(AnalysisRun).count()==1 and session.query(Forecast).count()==4
    assert client.get(f'/analysis/{data["id"]}').json()["location"]=="Spain"
    assert len(client.get("/forecasts").json())==4
