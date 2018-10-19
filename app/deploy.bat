del /s /q "src/lib"
rmdir /s /q "src/lib"
pip install -r requirements.txt --upgrade -t src/lib
echo Y | gcloud datastore create-indexes index.yaml
cd src
echo Y | gcloud app deploy