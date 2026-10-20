from desktop_pet.services.reminders import ProductivityStore
from desktop_pet.services.tasks import accept_cloud_copy,link_existing_task


def test_read_sync_deduplicates_preserves_local_conflicts_and_only_resolves_explicitly(tmp_path):
    store=ProductivityStore(tmp_path/'data.sqlite3')
    remote={'id':'cloud-1','title':'Cloud title','etag':'v1','status':'needsAction'}
    store.merge_tasks('list',[remote]);store.merge_tasks('list',[remote])
    assert len(store.tasks())==1
    task=store.tasks()[0];store.complete_task(task['id'])
    changed=dict(remote,title='Changed remotely',etag='v2')
    store.merge_tasks('list',[changed])
    local=store.task(task['id'])
    assert local['title']=='Cloud title' and local['status']=='completed' and local['conflict']
    accept_cloud_copy(store,local['id'],changed)
    local=store.task(local['id'])
    assert local['title']=='Changed remotely' and local['dirty']==0 and local['conflict']==''
    store.merge_tasks('list',[])
    assert store.task(local['id']) is not None


def test_uncertain_upload_can_link_existing_cloud_copy_without_duplicate_creation(tmp_path):
    store=ProductivityStore(tmp_path/'data.sqlite3')
    identifier=store.add_task('An uncertain upload')
    store.mark_task_issue(identifier,'Upload outcome unknown')
    remote={'id':'already-created','title':'An uncertain upload','etag':'v2'}
    store.merge_tasks('list',[remote]);assert len(store.tasks())==2
    link_existing_task(store,identifier,'list',remote)
    assert len(store.tasks())==1 and store.task(identifier)['external_id']=='already-created'
    assert store.task(identifier)['conflict']==''
