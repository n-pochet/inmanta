"""
    Copyright 2016 Inmanta

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

    Contact: bart@inmanta.com
"""
import uuid
import datetime
import time

from inmanta import data
from inmanta import const
import pytest
import pymongo
import logging


class Doc(data.BaseDocument):
    name = data.Field(field_type=str, required=True)
    field1 = data.Field(field_type=str, default=None)
    field2 = data.Field(field_type=bool, default=False)
    field3 = data.Field(field_type=list, default=[])
    field4 = data.Field(field_type=dict, default={})

    __indexes__ = [
        dict(keys=[("name", pymongo.ASCENDING)], unique=True)
    ]


class EnumDoc(data.BaseDocument):
    action = data.Field(field_type=const.ResourceAction, required=True)


@pytest.mark.gen_test
def test_motor(motor):
    yield motor.testCollection.insert_one({"a": 1, "b": "abcd"})
    results = yield motor.testCollection.find_one({"a": {"$gt": 0}})

    assert "_id" in results

    yield motor.testCollection.insert_one({"a": {"b": {"c": 1}}})
    results = motor.testCollection.find({})

    while (yield results.fetch_next):
        assert "a" in results.next_object()


def test_collection_naming():
    assert Doc.collection_name() == "Doc"


def test_ctor():
    # Mongo data should not contain an id
    with pytest.raises(AttributeError):
        Doc(from_mongo=True, id="1234")

    # ID is autogenerated for new objects
    with pytest.raises(AttributeError):
        Doc(from_mongo=True, id="1234")

    # Required attributes have to be set in the ctor
    with pytest.raises(AttributeError):
        Doc()

    # Only defined fields are allowed
    with pytest.raises(AttributeError):
        Doc(test="")

    # A required field cannot be none
    with pytest.raises(TypeError):
        Doc(name=None)

    # Fields require the correct type
    with pytest.raises(TypeError):
        Doc(name=1234)


def test_document_def():
    t = Doc(name="doc")
    with pytest.raises(TypeError):
        t.id = "1234"

    t.id = uuid.uuid4()
    json = t.to_dict()

    assert "id" in json
    assert "_id" in t.to_mongo()


@pytest.mark.gen_test
def test_document_insert(motor):
    Doc.set_connection(motor)

    d = Doc(name="test")

    yield d.insert()
    docs = yield motor.Doc.find({}).to_list(length=10)
    assert len(docs) == 1

    doc = yield Doc.get_by_id(d.id)
    assert doc.name == d.name


@pytest.mark.gen_test
def test_get_by_id(motor):
    Doc.set_connection(motor)

    d = Doc(name="test")
    yield d.insert()

    d1 = yield Doc.get_by_id(d.id)
    assert d1.name == d.name

    d2 = yield Doc.get_by_id(uuid.uuid4())
    assert d2 is None


@pytest.mark.gen_test
def test_defaults(motor):
    Doc.set_connection(motor)

    d = Doc(name="test")
    yield d.insert()

    assert d.to_dict()["field1"] is None
    assert not d.field2

    d2 = yield Doc.get_by_id(d.id)
    d2.insert()

    assert not d2.field2

    d.field3.append(1)


@pytest.mark.gen_test
def test_document_update(motor):
    Doc.set_connection(motor)

    d = Doc(name="test")
    yield d.insert()

    yield d.update(name="test2")
    result = yield motor.Doc.find_one({"name": "test2"})
    assert "name" in result


@pytest.mark.gen_test
def test_document_delete(motor):
    Doc.set_connection(motor)

    d = Doc(name="test")
    yield d.insert()
    yield Doc.delete_all(name="test")

    docs = yield Doc.get_list()
    assert len(docs) == 0


@pytest.mark.gen_test
def test_key_escape(motor):
    Doc.set_connection(motor)

    d = Doc(name="test")
    d.field4 = {"a.b": "1", "a$b": "2", "a\\b": "3", "a.b.c": 4}
    yield d.insert()

    d2 = yield Doc.get_by_id(d.id)

    for k in d.field4.keys():
        assert k in d2.field4


@pytest.mark.gen_test
def test_nested_key_escape(motor):
    Doc.set_connection(motor)

    d = Doc(name="test")
    d.field4["a0a7f22b-bc71-51f6-bc91-f2b0e368b786"] = {}
    d.field4["a0a7f22b-bc71-51f6-bc91-f2b0e368b786"]["changes"] = {}
    d.field4["a0a7f22b-bc71-51f6-bc91-f2b0e368b786"]["changes"]["routes"] = {}
    d.field4["a0a7f22b-bc71-51f6-bc91-f2b0e368b786"]["changes"]["routes"]["current"] = {}
    d.field4["a0a7f22b-bc71-51f6-bc91-f2b0e368b786"]["changes"]["routes"]["current"]["172.19.0.0/16"] = "1.1.1.1"
    yield d.insert()

    yield Doc.get_by_id(d.id)


@pytest.mark.gen_test
def test_enum_field(motor):
    EnumDoc.set_connection(motor)

    d = EnumDoc(action=const.ResourceAction.deploy)
    yield d.insert()

    new = yield EnumDoc.get_by_id(d.id)

    assert new.action is const.ResourceAction.deploy
    assert new.to_dict()["action"] == const.ResourceAction.deploy


@pytest.mark.gen_test
def test_project(data_module):
    project = data.Project(name="test")
    yield project.insert()

    projects = yield data.Project.get_list(name="test")
    assert len(projects) == 1
    assert projects[0].id == project.id

    other = yield data.Project.get_by_id(project.id)
    assert project != other
    assert project.id == other.id


@pytest.mark.gen_test
def test_project_unique(data_module):
    project = data.Project(name="test")
    yield project.insert()

    project = data.Project(name="test")
    with pytest.raises(pymongo.errors.DuplicateKeyError):
        yield project.insert()


@pytest.mark.gen_test
def test_environment(data_module):
    project = data.Project(name="test")
    yield project.insert()

    env = data.Environment(name="dev", project=project.id, repo_url="", repo_branch="")
    yield env.insert()
    assert env.project == project.id

    yield project.delete_cascade()

    projects = yield data.Project.get_list()
    envs = yield data.Environment.get_list()
    assert len(projects) == 0
    assert len(envs) == 0


@pytest.mark.gen_test
def test_agent_process(data_module):
    project = data.Project(name="test")
    yield project.insert()

    env = data.Environment(name="dev", project=project.id, repo_url="", repo_branch="")
    yield env.insert()

    agent_proc = data.AgentProcess(hostname="testhost",
                                   environment=env.id,
                                   first_seen=datetime.datetime.now(),
                                   last_seen=datetime.datetime.now(),
                                   sid=uuid.uuid4())
    yield agent_proc.insert()

    agi1 = data.AgentInstance(process=agent_proc.id, name="agi1", tid=env.id)
    yield agi1.insert()
    agi2 = data.AgentInstance(process=agent_proc.id, name="agi2", tid=env.id)
    yield agi2.insert()

    agent = data.Agent(environment=env.id, name="agi1", last_failover=datetime.datetime.now(), paused=False, primary=agi1.id)
    agent = yield agent.insert()

    agents = yield data.Agent.get_list()
    assert len(agents) == 1
    agent = agents[0]

    primary_instance = yield data.AgentInstance.get_by_id(agent.primary)
    primary_process = yield data.AgentProcess.get_by_id(primary_instance.process)
    assert primary_process.id == agent_proc.id


@pytest.mark.gen_test
def test_config_model(data_module):
    project = data.Project(name="test")
    yield project.insert()

    env = data.Environment(name="dev", project=project.id, repo_url="", repo_branch="")
    yield env.insert()

    version = int(time.time())
    cm = data.ConfigurationModel(environment=env.id, version=version, date=datetime.datetime.now(),
                                 total=1, version_info={})
    yield cm.insert()

    # create resources
    key = "std::File[agent1,path=/etc/motd]"
    res1 = data.Resource.new(environment=env.id, resource_version_id=key + ",v=%d" % version, attributes={"path": "/etc/motd"})
    yield res1.insert()

    agents = yield data.ConfigurationModel.get_agents(env.id, version)
    assert len(agents) == 1
    assert "agent1" in agents


@pytest.mark.gen_test
def test_model_list(data_module):
    env_id = uuid.uuid4()

    for version in range(1, 20):
        cm = data.ConfigurationModel(environment=env_id, version=version, date=datetime.datetime.now(), total=0,
                                     version_info={})
        yield cm.insert()

    versions = yield data.ConfigurationModel.get_versions(env_id, 0, 1)
    assert len(versions) == 1
    assert versions[0].version == 19

    versions = yield data.ConfigurationModel.get_versions(env_id, 1, 1)
    assert len(versions) == 1
    assert versions[0].version == 18

    versions = yield data.ConfigurationModel.get_versions(env_id)
    assert len(versions) == 19
    assert versions[0].version == 19
    assert versions[-1].version == 1

    versions = yield data.ConfigurationModel.get_versions(env_id, 10)
    assert len(versions) == 9
    assert versions[0].version == 9
    assert versions[-1].version == 1


@pytest.mark.gen_test
def test_resource_purge_on_delete(data_module):
    env_id = uuid.uuid4()
    version = 1
    # model 1
    cm1 = data.ConfigurationModel(environment=env_id, version=version, date=datetime.datetime.now(), total=2, version_info={},
                                  released=True, deployed=True)
    yield cm1.insert()

    res11 = data.Resource.new(environment=env_id, resource_version_id="std::File[agent1,path=/etc/motd],v=%s" % version,
                              status=const.ResourceState.deployed,
                              attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": False})
    yield res11.insert()

    res12 = data.Resource.new(environment=env_id, resource_version_id="std::File[agent2,path=/etc/motd],v=%s" % version,
                              status=const.ResourceState.deployed,
                              attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": True})
    yield res12.insert()

    # model 2 (multiple undeployed versions)
    while version < 10:
        version += 1
        cm2 = data.ConfigurationModel(environment=env_id, version=version, date=datetime.datetime.now(), total=1,
                                      version_info={}, released=False, deployed=False)
        yield cm2.insert()

        res21 = data.Resource.new(environment=env_id, resource_version_id="std::File[agent5,path=/etc/motd],v=%s" % version,
                                  status=const.ResourceState.available,
                                  attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": False})
        yield res21.insert()

    # model 3
    version += 1
    cm3 = data.ConfigurationModel(environment=env_id, version=version, date=datetime.datetime.now(), total=0, version_info={})
    yield cm3.insert()

    to_purge = yield data.Resource.get_deleted_resources(env_id, version)

    assert len(to_purge) == 1
    assert to_purge[0].model == 1
    assert to_purge[0].resource_id == "std::File[agent1,path=/etc/motd]"


@pytest.mark.gen_test
def test_issue_422(data_module):
    env_id = uuid.uuid4()
    version = 1
    # model 1
    cm1 = data.ConfigurationModel(environment=env_id, version=version, date=datetime.datetime.now(), total=1, version_info={},
                                  released=True, deployed=True)
    yield cm1.insert()

    res11 = data.Resource.new(environment=env_id, resource_version_id="std::File[agent1,path=/etc/motd],v=%s" % version,
                              status=const.ResourceState.deployed,
                              attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": False})
    yield res11.insert()

    # model 2 (multiple undeployed versions)
    version += 1
    cm2 = data.ConfigurationModel(environment=env_id, version=version, date=datetime.datetime.now(), total=1,
                                  version_info={}, released=False, deployed=False)
    yield cm2.insert()

    res21 = data.Resource.new(environment=env_id, resource_version_id="std::File[agent1,path=/etc/motd],v=%s" % version,
                              status=const.ResourceState.available,
                              attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": False})
    yield res21.insert()

    # model 3
    version += 1
    cm3 = data.ConfigurationModel(environment=env_id, version=version, date=datetime.datetime.now(), total=0, version_info={})
    yield cm3.insert()

    to_purge = yield data.Resource.get_deleted_resources(env_id, version)

    assert len(to_purge) == 1
    assert to_purge[0].model == 1
    assert to_purge[0].resource_id == "std::File[agent1,path=/etc/motd]"


@pytest.mark.gen_test
def test_get_latest_resource(data_module):
    env_id = uuid.uuid4()
    key = "std::File[agent1,path=/etc/motd]"
    res11 = data.Resource.new(environment=env_id, resource_version_id=key + ",v=1", status=const.ResourceState.deployed,
                              attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": False})
    yield res11.insert()

    res12 = data.Resource.new(environment=env_id, resource_version_id=key + ",v=2", status=const.ResourceState.deployed,
                              attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": True})
    yield res12.insert()

    res = yield data.Resource.get_latest_version(env_id, key)
    assert res.model == 2


@pytest.mark.gen_test
def test_snapshot(data_module):
    env_id = uuid.uuid4()

    snap = data.Snapshot(environment=env_id, model=1, name="a", started=datetime.datetime.now(), resources_todo=1)
    yield snap.insert()

    s = yield data.Snapshot.get_by_id(snap.id)
    yield s.resource_updated(10)
    assert s.resources_todo == 0
    assert s.total_size == 10
    assert s.finished is not None

    s = yield data.Snapshot.get_by_id(snap.id)
    assert s.resources_todo == 0
    assert s.total_size == 10
    assert s.finished is not None

    yield s.delete_cascade()
    result = yield data.Snapshot.get_list()
    assert len(result) == 0


@pytest.mark.gen_test
def test_resource_action(data_module):
    env_id = uuid.uuid4()
    action_id = uuid.uuid4()

    resource_action = data.ResourceAction(environment=env_id, resource_version_ids=[], action_id=action_id,
                                          action=const.ResourceAction.deploy, started=datetime.datetime.now())
    yield resource_action.insert()

    resource_action.add_changes({"rid": {"field1": {"old": "a", "new": "b"}, "field2": {}}})
    yield resource_action.save()

    resource_action.add_changes({"rid": {"field2": {"old": "c", "new": "d"}, "field3": {}}})
    yield resource_action.save()

    resource_action.add_logs([{}, {}])
    yield resource_action.save()

    resource_action.add_logs([{}, {}])
    yield resource_action.save()

    ra = yield data.ResourceAction.get_by_id(resource_action.id)
    assert len(ra.changes["rid"]) == 3
    assert len(ra.messages) == 4

    assert ra.changes["rid"]["field1"]["old"] == "a"
    assert ra.changes["rid"]["field1"]["new"] == "b"
    assert ra.changes["rid"]["field2"]["old"] == "c"
    assert ra.changes["rid"]["field2"]["new"] == "d"
    assert ra.changes["rid"]["field3"] == {}


@pytest.mark.gen_test
def test_get_resources(data_module):
    env_id = uuid.uuid4()
    resource_ids = []
    for i in range(1, 11):
        res = data.Resource.new(environment=env_id, resource_version_id="std::File[agent1,path=/tmp/file%d],v=1" % i,
                                status=const.ResourceState.deployed,
                                attributes={"path": "/etc/motd", "purge_on_delete": True, "purged": False})
        yield res.insert()
        resource_ids.append(res.resource_version_id)

    resources = yield data.Resource.get_resources(env_id, resource_ids)
    assert len(resources) == len(resource_ids)
    assert sorted([x.resource_version_id for x in resources]) == sorted(resource_ids)

    resources = yield data.Resource.get_resources(env_id, [resource_ids[0], "abcd"])
    assert len(resources) == 1


@pytest.mark.gen_test
def test_escaped_resources(data_module):
    env_id = uuid.uuid4()
    routes = {"8.0.0.0/8": "1.2.3.4", "0.0.0.0/0": "127.0.0.1"}
    res = data.Resource.new(environment=env_id, resource_version_id="std::File[agent1,name=router],v=1",
                            status=const.ResourceState.deployed,
                            attributes={"name": "router", "purge_on_delete": True, "purged": False, "routes": routes})
    yield res.insert()
    resource_id = res.resource_version_id

    resources = yield data.Resource.get_resources(env_id, [resource_id])
    assert len(resources) == 1

    assert resources[0].attributes["routes"] == routes


@pytest.mark.gen_test
def test_data_document_recursion(data_module):
        env_id = uuid.uuid4()
        now = datetime.datetime.now()
        ra = data.ResourceAction(environment=env_id, resource_version_ids=["id"], action_id=uuid.uuid4(),
                                 action=const.ResourceAction.store, started=now, finished=now,
                                 messages=[data.LogLine.log(logging.INFO, "Successfully stored version %(version)d",
                                                            version=2)])
        yield ra.insert()
