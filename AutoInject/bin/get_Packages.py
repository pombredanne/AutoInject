import pymongo
from pymongo import MongoClient
from subprocess import check_output

client                  = MongoClient()
db                      = client['package_db']
collection              = db['package_list']

def insert_Packages():
    
    out                 = check_output(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\n"])
    tmp                 = out.split('\n')

    # Deleting any current package details
    db.package_list.drop()
    print('Collection names (should be empty):', db.collection_names())
    
    for line in tmp:
        package_array   = line.split('\t')

        try:
            package_item = {
                'package_name' : package_array[0],
                'version' : package_array[1],
                'architecture' : package_array[2]
            }
        
        except:
            print("Error inserting", package_array)
            continue
        
        result = collection.insert_one(package_item)

    print('Finished inserting into DB')
    python_data = collection.find_one({ 'package_name' : 'python' })
    print(python_data)

def get_Packages():

    package_JSON = collection.find({})
    for document in package_JSON:
        print(document)

get_Packages()