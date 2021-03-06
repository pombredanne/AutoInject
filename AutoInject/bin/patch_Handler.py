import pymongo, re, time, os

from AutoInject.bin.website_Parser import perform_Package_Version_Update

from collections        import defaultdict
from datetime           import datetime
from pymongo            import MongoClient
from subprocess         import check_output, call
from difflib            import unified_diff
from shutil             import copyfile

from json               import loads
from bson.json_util     import dumps

client                      = MongoClient()
package_collection          = client['package_db']['package_list']
cve_collection              = client['cvedb']['cves']

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
#                           BFS Related Functions                          |
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------

def produce_Diff_Of_Files(file_path1, file_path2, package_name, diff_file_name):    

    if not os.path.exists('AutoInject/file_store'):
        os.makedirs('AutoInject/file_store')

    if not os.path.exists('AutoInject/file_store/' + package_name):
        os.makedirs('AutoInject/file_store/' + package_name)

    if (os.path.exists(file_path1) and os.path.exists(file_path2)):
        file_path_of_diff_file = "AutoInject/file_store/" + package_name
        
        if not os.path.exists(file_path_of_diff_file): 
            os.makedirs(file_path_of_diff_file)
        
        full_file_path = file_path_of_diff_file + "/" + diff_file_name

        iteration = 1
        while (os.path.exists(full_file_path)):
            iteration += 1
            full_file_path = file_path_of_diff_file + "/" + str(iteration) + diff_file_name

        with open(full_file_path, "w") as outfile:
            with open(file_path1, "U") as file1:
                with open(file_path2, "U") as file2:
                    for lines in unified_diff(file1.readlines(), file2.readlines(), 
                        fromfile=file_path2, tofile=file_path1, fromfiledate=get_Current_Time(), tofiledate=get_Current_Time()):
                        outfile.write(lines)
                    outfile.write('\n')
    
    else: print("Path to files does not exist")
    
    if full_file_path: return full_file_path
    else: return False

def upload_File(package_name, original_files_path, diff_file_path, type_of_update, type_of_implementation, comment, 
    type_of_patch, copy_of_file_path, active):

    print("Package name is:", package_name)

    package_collection.update(
        { 'package_name' : package_name },
        { '$push' : {
            'log' : { 
                'original_files_path' : original_files_path,
                'file_path_of_diff' : diff_file_path, 
                'date' : str(datetime.now()),
                'update_type' : type_of_update, # build_from_source / version
                'comment' : comment, 
                'implementation_type' : type_of_implementation, # manual / automatic
                'type_of_patch' : type_of_patch, # forward / backward
                'file_path_of_copy' : copy_of_file_path,
                'active' : active, # 1 -> active, 0 -> not active
                'path_of_intermediate_store' : 'N/A'
            }
        } }
    )

def handle_Patch_Maintenance(package_name, date_of_patch):
    reverser = package_collection.find_one( { 
        'package_name' : package_name,
        'log' : { '$elemMatch' :  { 
            'date' : date_of_patch,
            'active' : 1 
        } }
    } )

    if reverser:
        formatted_data = loads(dumps(reverser))
        for elements in formatted_data['log']:
            if (elements['date'] == date_of_patch):
                if (elements['update_type'] == 'version'):
                    if (elements['type_of_patch'] == 'backward_patch'): 
                        apply_Version_Reversal(elements, reverser['package_name'])
                    elif (elements['type_of_patch'] == 'forward_patch'):
                        apply_Version_Forward(elements, reverser['package_name'])
                elif (elements['update_type'] == 'build_from_source'):
                    if (elements['type_of_patch'] == 'backward_patch'): 
                        apply_BFS_Reversal(elements, package_name)
                    elif (elements['type_of_patch'] == 'forward_patch'):
                        apply_BFS_Forward(elements)
                return True
    else: print("No file matching"); return False

def apply_BFS_Reversal(json_of_patch, package_name):

    if (json_of_patch['path_of_intermediate_store'] == 'N/A'):
        copy_name = make_Copy_Of_File(package_name, json_of_patch['original_files_path'])
    else:
        copy_name = make_Copy_Of_File("--", json_of_patch['original_files_path'], json_of_patch['path_of_intermediate_store'])

    # Update the reversal patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : 
                {   'file_path_of_copy' : json_of_patch['file_path_of_copy'],
                    'active' : 1,
                    'type_of_patch' : 'backward_patch' } 
            } 
        },
        { '$set' : { 'log.$.path_of_intermediate_store' : copy_name, 'log.$.active' : 0 } }
    )
    # Update the forward patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : 
                {   'file_path_of_copy' : json_of_patch['file_path_of_copy'],
                    'active' : 0,
                    'type_of_patch' : 'forward_patch' } 
            } 
        },
        { '$set' : { 'log.$.path_of_intermediate_store' : copy_name, 'log.$.active' : 1 } }
    )

    with open(json_of_patch['file_path_of_copy'], 'r') as file_to_read:
        content_of_file = file_to_read.read()
        with open(json_of_patch['original_files_path'], 'w') as file_to_write:
            file_to_write.write(content_of_file)

    restore_File_Contents(json_of_patch['file_path_of_diff'])

def apply_BFS_Forward(json_of_patch):

    with open(json_of_patch['path_of_intermediate_store'], 'r') as file_to_read:
        content_of_file = file_to_read.read()
        with open(json_of_patch['original_files_path'], 'w') as file_to_write:
            file_to_write.write(content_of_file)

    # Update the reversal patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : 
                {   'file_path_of_copy' : json_of_patch['file_path_of_copy'],
                    'active' : 1,
                    'type_of_patch' : 'forward_patch' } 
            } 
        },
        { '$set' : { 'log.$.active' : 0 } }
    )
    # Update the forward patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : 
                {   'file_path_of_copy' : json_of_patch['file_path_of_copy'],
                    'active' : 0,
                    'type_of_patch' : 'backward_patch' } 
            } 
        },
        { '$set' : { 'log.$.active' : 1 } }
    )

def delete_Patch(package_name, date_of_patch):
    tmp = package_collection.find_one( { 
        'package_name' : package_name, 
        'log' : { '$elemMatch' :  { 'date' : date_of_patch, 'active' : 1 } } 
    } )
    file_path_of_copy   = False
    version_delete      = False
    bfs_delete          = False
    
    if tmp:
        for values in tmp['log']:
            if (values['date'] == date_of_patch):
                if (values['update_type'] == 'version'): version_delete = True
                elif (values['update_type'] == 'build_from_source'): bfs_delete = True
    
    if version_delete:
        for values in tmp['log']:
            if (values['date'] == date_of_patch):
                package_collection.update(
                    { '_id' : tmp['_id'] },
                    { '$pull' : { 'log' : { 'linking_id' : values['linking_id'] } } }
                )
    elif bfs_delete:
        for values in tmp['log']:
            if (values['date'] == date_of_patch):
                if values['path_of_intermediate_store']:
                    if (os.path.isfile(get_Source_Path(values['path_of_intermediate_store']))): 
                        os.remove(values['path_of_intermediate_store'])
                if (os.path.isfile(get_Source_Path(values['file_path_of_copy']))): os.remove(values['file_path_of_copy'])
                if (os.path.isfile(get_Source_Path(values['file_path_of_diff']))): os.remove(values['file_path_of_diff'])
                file_path_of_copy = values['file_path_of_copy']     
        for values in tmp['log']:       
            if (values['file_path_of_copy'] == file_path_of_copy and values['active'] == 0): 
                if values['path_of_intermediate_store']:
                    if (os.path.isfile(get_Source_Path(values['path_of_intermediate_store']))): 
                        os.remove(values['path_of_intermediate_store'])
                if (os.path.isfile(values['file_path_of_diff'])): os.remove(values['file_path_of_diff'])

        if file_path_of_copy:
            package_collection.update(
                { '_id' : tmp['_id'] },
                { '$pull' : { 'log' : { 'file_path_of_copy' : file_path_of_copy } } }
            )

    else: return False

def make_Copy_Of_File(package_name, file_path, set_path=False):

    if set_path:
        copyfile(file_path, set_path)
        return set_Path
    else:
        copy = "AutoInject/file_store/" + package_name + "/copy"
        count = 0
        while (os.path.exists(copy)):
            count += 1
            copy = "AutoInject/file_store/" + package_name + "/copy" + str(count)
        copyfile(file_path, copy)
        return get_Source_Path(copy)

def restore_File_Contents(path_of_diff):
    os.system("patch --no-backup-if-mismatch --force -d/ -p0 < " + path_of_diff)

kwargs  = {
    'c' : {
        'compile' : True,
        'command' : 'gcc -c <package>'
    },
    'java' : { 
        'compile' : True,
        'command' : 'javac <package>'
    }
}
list_Of_Compiler_Procedures = defaultdict(dict, **kwargs)

def compile_File(path_of_file):
    os_call = check_If_Needs_To_Be_Compiled(path_of_file)
    if os_call:
        os_call = os_call.replace("<package>", path_of_file)
        try:    os.system(os_call)
        except: return False

def check_If_Needs_To_Be_Compiled(path_of_file):
    if (os.path.exists(path_of_file)): 
        file_ext = get_File_Name_From_Path(path_of_file)
        print(file_ext)
    for key, value in list_Of_Compiler_Procedures.items():
        if key in file_ext:
            if value['compile']: return value['command']
    return False

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
#                           Version Related Functions                      |
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
        
def apply_Version_Reversal(json_of_patch, package):
    print("Reversing version update")

    if not perform_Package_Version_Update(
        None, 
        package,
        None,
        json_of_patch['original_files_path']
    ): return False

    print("Updating log information")
    # Update the reversal patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : {   
                'linking_id' : json_of_patch['linking_id'],
                'active' : 1,
                'type_of_patch' : 'backward_patch' } 
            } 
        },
        { '$set' : { 'log.$.active' : 0 } }
    )
    # Update the forward patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : {   
                'linking_id' : json_of_patch['linking_id'],
                'active' : 0,
                'type_of_patch' : 'forward_patch' } 
            } 
        },
        { '$set' : { 'log.$.active' : 1 } }
    )

def apply_Version_Forward(json_of_patch, package):
    print("Reversing version update")

    if not perform_Package_Version_Update(
        None, 
        package,
        None,
        json_of_patch['original_files_path']
    ): return False

    # Update the reversal patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : {   
                'linking_id' : json_of_patch['linking_id'],
                'active' : 1,
                'type_of_patch' : 'forward_patch' } 
            } 
        },
        { '$set' : { 'log.$.active' : 0 } }
    )
    # Update the forward patch
    package_collection.update_one(
        {   'log' : 
            { '$elemMatch' : {   
                'linking_id' : json_of_patch['linking_id'],
                'active' : 0,
                'type_of_patch' : 'backward_patch' } 
            } 
        },
        { '$set' : { 'log.$.active' : 1 } }
    )

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
#                           System Related Functions                       |
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------

def get_Source_Path(path_of_file):
    return os.path.realpath(path_of_file)

def get_Current_Time():
    formatted_time = datetime.utcnow()
    formatted_time = str(formatted_time).split(' ')[1] + ' +0000'
    return formatted_time

def get_File_Name_From_Path(path_of_file):
    return os.path.basename(path_of_file)
