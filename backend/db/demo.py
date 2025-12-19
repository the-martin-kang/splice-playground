from supabase import create_client, Client

SUPABASE_URL='https://lcluumakpmftnletdbtq.supabase.co'
SUPABASE_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxjbHV1bWFrcG1mdG5sZXRkYnRxIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTcwNzg1MCwiZXhwIjoyMDgxMjgzODUwfQ.lAawXk1sxLXzBhkMMf-TQ_CV3ct7KOfIrhvWEJMj6Os'
# publish용, service용 secret키가 있고 이는 그중 secret키임

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Insert a new row into table
# new_row = {'first_name': 'John Doe'}
# supabase.table('demo-table').insert(new_row).execute()

# # update a row
# new_row = {'first_name': 'Jane Doe'}
# supabase.table('demo-table').update(new_row).eq('id', 2).execute()


# Delete record
# supabase.table('demo-table').delete().eq('id', 2).execute()


# results = supabase.table('demo-table').select('*').execute()
# print(results)


###### render a photo!!
response = supabase.storage.from_('demo-bucket').get_public_url('snu_ui_download.png')
# url을 반환해준다!
print(response)