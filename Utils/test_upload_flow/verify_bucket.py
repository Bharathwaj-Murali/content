import argparse
import functools
import json
import os
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile
from packaging.version import Version

from Tests.Marketplace.marketplace_services import init_storage_client
from Tests.Marketplace.upload_packs import download_and_extract_index
from Tests.scripts.utils.log_util import install_logging
from Tests.scripts.utils import logging_wrapper as logging
from Tests.scripts.utils.log_util import install_logging

MSG_DICT = {
    'verify_new_pack': 'Verify the pack is in the index, verify version 1.0.0 zip exists under the pack path',
    'verify_modified_pack': 'Verify the packs new version is in the index, verify the new version zip exists under '
                            'the packs path, verify all the new items are present in the pack',
    'verify_new_version': 'Verify a new version exists in the index, verify the rn is parsed correctly to the '
                          'changelog',
    'verify_rn': 'Verify the content of the RN is in the changelog under the right version',
    'verify_hidden': 'Verify the pack does not exist in index',
    'verify_readme': 'Verify readme content is parsed correctly, verify that there was no version bump '
                     'if only readme was modified',
    'verify_failed_pack': 'Verify commit hash is not updated in the pack metadata in the index.zip',
    # 'verify_modified_path': 'Verify the path of the item is modified',
    'verify_modified_modeling_rule_path': 'Verify the path of the item is modified',
    'verify_dependency': 'Verify the new dependency is in the metadata',
    'verify_new_image': 'Verify the new image was uploaded'
}
XSOAR_BUCKET = 'marketplace-dist-dev'
XSIAM_BUCKET = 'marketplace-v2-dist-dev'


def logger(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        logging.info(f'Starting {func.__name__}')
        print(f'Starting {func.__name__}')
        try:
            result, pack_id = func(self, *args, **kwargs)
            self.is_valid = self.is_valid and result
            logging.info(f'Result of {func.__name__} - {MSG_DICT[func.__name__]} for {pack_id} is {result}')
            # print(f'Result of {func.__name__} - {MSG_DICT[func.__name__]} for {pack_id} is {result}')
            # # TODO: remove all prints once logging is present in the gitlab build
        except FileNotFoundError as e:
            logging.info(f'Result of {func.__name__} - {MSG_DICT[func.__name__]} is False: {e}')
            # print(f'Result of {func.__name__} - {MSG_DICT[func.__name__]} is False:\nException: {e}')
            self.is_valid = False

    return wrapper


class GCP:
    def __init__(self, service_account, storage_bucket_name, storage_base_path):
        storage_client = init_storage_client(service_account)
        self.storage_bucket = storage_client.bucket(storage_bucket_name)
        self.storage_base_path = storage_base_path

        self.extracting_destination = tempfile.mkdtemp()
        self.index_path, _, _ = download_and_extract_index(self.storage_bucket, self.extracting_destination,
                                                           self.storage_base_path)
        # TODO: for testing, use these lines instead of the 2 above
        # self.extracting_destination = os.path.join(os.getcwd(), 'results')
        # self.index_path = '/Users/nmaimon/dev/demisto/content/Utils/test_upload_flow/results/index'
        # TODO: download the index once to this path and then work with it, instead of downloading it again and again

    def download_and_extract_pack(self, pack_id, pack_version):
        pack_path = os.path.join(self.storage_base_path, pack_id, pack_version, f"{pack_id}.zip")
        pack = self.storage_bucket.blob(pack_path)
        if pack.exists():
            download_pack_path = os.path.join(self.extracting_destination, f"{pack_id}.zip")
            pack.download_to_filename(download_pack_path)
            with ZipFile(download_pack_path, 'r') as pack_zip:
                pack_zip.extractall(os.path.join(self.extracting_destination, pack_id))
            return os.path.join(self.extracting_destination, pack_id)
        else:
            raise FileNotFoundError(f'{pack_id} pack of version {pack_version} was not found in the bucket')

    def download_image(self, pack_id):
        image_path = os.path.join(self.storage_base_path, pack_id, f"{pack_id}_image.png")
        image = self.storage_bucket.blob(image_path)
        if image.exists():
            download_image_path = os.path.join(self.extracting_destination, f"{pack_id}_image.png")
            image.download_to_filename(download_image_path)
            return download_image_path
        else:
            raise FileNotFoundError(f'Image of pack {pack_id} was not found in the bucket')

    def is_in_index(self, pack_id):
        pack_path = os.path.join(self.index_path, pack_id)
        return os.path.exists(pack_path)

    def get_changelog_rn_by_version(self, pack_id, version):
        changelog_path = os.path.join(self.index_path, pack_id, 'changelog.json')
        changelog = read_json(changelog_path)
        return changelog.get(version, {}).get('releaseNotes', '')

    def get_pack_metadata(self, pack_id):
        """
        returns the metadata.json of the latest pack version from the pack's zip
        """
        metadata_path = os.path.join(self.extracting_destination, 'index', pack_id, 'metadata.json')
        return read_json(metadata_path)

    def is_items_in_pack(self, item_file_paths: list):
        """
        Check if an item is inside the pack.
        """
        not_exists = []
        for item_path in item_file_paths:
        # item_name_with_extension = Path(item_file_paths).name
            if not os.path.exists(os.path.join(self.extracting_destination, item_path)):
                not_exists.append(item_path)
        # exists = os.path.exists(extracted_item_path)
        if not_exists:
            raise FileNotFoundError(f"The following files were not found in the bucket: '{not_exists}'")
        return True

    def get_index_json(self):
        index_json_path = os.path.join(self.storage_base_path, 'index.json')
        index_json = self.storage_bucket.blob(index_json_path)
        if index_json.exists():
            download_index_path = os.path.join(self.extracting_destination, 'index.json')
            index_json.download_to_filename(download_index_path)
            return read_json(download_index_path)
        else:
            raise FileNotFoundError('index.json was not found in the bucket')

    def get_flow_commit_hash(self):
        index_json = self.get_index_json()
        return index_json.get('commit')

    def get_max_version(self, pack_id):
        changelog = self.get_changelog(pack_id)
        return str(max([Version(key) for key, value in changelog.items()]))

    def get_changelog(self, pack_id):
        changelog_path = os.path.join(self.index_path, pack_id, 'changelog.json')
        return read_json(changelog_path)

    def get_pack_readme(self, pack_id):
        item_path = os.path.join(self.extracting_destination, pack_id, 'README.md')
        with open(item_path, 'r') as f:
            return f.read()


class BucketVerifier:
    def __init__(self, gcp: GCP, bucket_name, versions_dict, items_dict):
        self.gcp = gcp
        self.bucket_name = bucket_name
        self.versions = versions_dict
        self.items_dict = items_dict
        self.is_valid = True

    @logger
    def verify_new_pack(self, pack_id, pack_items):
        """
        Verify the pack is in the index, verify version 1.0.0 zip exists under the pack's path
        """
        version_exists = [self.gcp.is_in_index(pack_id), self.gcp.download_and_extract_pack(pack_id, '1.0.0')]
        items_exists = [self.gcp.is_items_in_pack(item_file_paths) for item_file_paths
                        in pack_items.values()]
        return all(version_exists) and all(items_exists), pack_id

    @logger
    def verify_modified_pack(self, pack_id, pack_items, expected_rn):
        """
        Verify the pack's new version is in the index, verify the new version zip exists under the pack's path,
        verify all the new items are present in the pack
        """
        self.gcp.download_and_extract_pack(pack_id, self.versions[pack_id])
        changelog_as_expected = expected_rn in self.gcp.get_changelog_rn_by_version(pack_id, self.versions[pack_id])
        items_exists = [self.gcp.is_items_in_pack(item_file_paths) for item_file_paths
                        in pack_items.values()]
        return changelog_as_expected and all(items_exists), pack_id

    @logger
    def verify_new_version(self, pack_id, rn):
        """
        Verify a new version exists in the index, verify the rn is parsed correctly to the changelog
        """
        new_version_exists = self.gcp.download_and_extract_pack(pack_id, self.versions[pack_id])
        new_version_exists_in_changelog = rn in self.gcp.get_changelog_rn_by_version(pack_id, self.versions[pack_id])
        new_version_exists_in_metadata = self.gcp.get_pack_metadata(pack_id).get('currentVersion') == self.versions[pack_id]
        return all([new_version_exists, new_version_exists_in_changelog, new_version_exists_in_metadata]), pack_id

    @logger
    def verify_rn(self, pack_id, rn):
        """
        Verify the content of the RN is in the changelog under the right version
        """
        return rn in self.gcp.get_changelog_rn_by_version(pack_id, self.versions[pack_id]), pack_id

    @logger
    def verify_hidden(self, pack_id):
        """
        Verify the pack does not exist in index
        """
        return not self.gcp.is_in_index(pack_id), pack_id

    @logger
    def verify_readme(self, pack_id, readme):
        """
        Verify readme content is parsed correctly, verify that there was no version bump if only readme was modified
        """
        self.gcp.download_and_extract_pack(pack_id, self.versions[pack_id])
        return self.gcp.get_max_version(pack_id) and readme in self.gcp.get_pack_readme(pack_id), pack_id

    @logger
    def verify_failed_pack(self, pack_id):
        """
        Verify commit hash is not updated in the pack's metadata in the index.zip
        """
        return self.gcp.get_flow_commit_hash() != self.gcp.get_pack_metadata(pack_id).get('commit'), pack_id

    # @logger
    # def verify_modified_path(self, pack_id, item_file_path):
    #     """
    #     Verify the path of the item is modified
    #     """

    #     self.gcp.download_and_extract_pack(pack_id, self.versions[pack_id])
    #     return self.gcp.is_items_in_pack([item_file_path]), pack_id

    @logger
    def verify_modified_modeling_rule_path(self, pack_id, modeling_rule, pack_items):
        """
        Verify the path of the item is modified
        """

        self.gcp.download_and_extract_pack(pack_id, self.versions[pack_id])
        # modeling_rule_paths = [modeling_rule / f"{modeling_rule.name}.xif", modeling_rule / f"{modeling_rule.name}.yml",
        #                        modeling_rule / f"{modeling_rule.name}_schema.json"]
        items_exists = [self.gcp.is_items_in_pack(item_file_paths) for item_file_paths
                        in pack_items.values()]
        return all(items_exists), pack_id

    @logger
    def verify_dependency(self, pack_id, dependency_id):
        """
        Verify the new dependency is in the metadata
        """
        # TODO: Should verify the dependency in the pack zip metadata as well - after CIAC-4686 is fixed
        return dependency_id in self.gcp.get_pack_metadata(pack_id).get('dependencies', {}).keys(), pack_id

    @logger
    def verify_new_image(self, pack_id, new_image_path):
        """
        Verify the new image was uploaded
        """
        image_in_bucket_path = self.gcp.download_image(pack_id)
        return open(image_in_bucket_path, "rb").read() == open(str(new_image_path), "rb").read(), pack_id

    def run_basic_validations(self):
        """
        Runs the basic verifications for both buckets.
        """
        # Case 1: Verify new pack - TestUploadFlow
        self.verify_new_pack('TestUploadFlow', self.items_dict.get('TestUploadFlow'))

        # Case 2: Verify modified pack - Armorblox
        expected_rn = 'testing adding new RN'
        self.verify_modified_pack('Armorblox', self.items_dict.get('Armorblox'), expected_rn)

        # Case 3: Verify dependencies handling - Armis
        self.verify_dependency('Armis', 'TestUploadFlow')

        # Case 4: Verify new version - ZeroFox
        expected_rn = 'testing adding new RN'
        self.verify_new_version('ZeroFox', expected_rn)

        # Case 5: Verify modified existing release notes - Box
        expected_rn = 'testing modifying existing RN'
        self.verify_rn('Box', expected_rn)

        # Case 6: Verify 1.0.0 rn was added - TestUploadFlow
        expected_rn = """\n#### Integrations\n##### TestUploadFlow\nfirst release note"""
        self.verify_rn('TestUploadFlow', expected_rn)

        # Case 7: Verify pack is set to hidden - Microsoft365Defender
        # self.verify_hidden('Microsoft365Defender')  TODO: fix after hidden pack mechanism is fixed

        # Case 8: Verify changed readme - Maltiverse
        expected_readme = 'readme test upload flow'
        self.verify_readme('Maltiverse', expected_readme)

        # Case 9: Verify failing pack - Absolute
        self.verify_failed_pack('Absolute')

        # Case 10: Verify changed image - Armis
        self.verify_new_image('Armis', Path(
            __file__).parent / 'TestUploadFlow' / 'Integrations' / 'TestUploadFlow' / 'TestUploadFlow_image.png')

    def run_xsiam_bucket_validations(self):
        """
        Runs the XSIAM verifications.
        """
        self.verify_modified_modeling_rule_path('AlibabaActionTrail', Path(os.path.join('AlibabaActionTrail', 'ModelingRules')),
                                                self.items_dict.get('AlibabaActionTrail'))
        # self.verify_modified_path('AlibabaActionTrail',
        #                           os.path.join('AlibabaActionTrail', 'ModelingRules', 'Alibaba.xif'))
        # self.verify_modified_path('AlibabaActionTrail',
        #                           os.path.join('AlibabaActionTrail', 'ModelingRules', 'Alibaba.yml'))
        # self.verify_modified_path('AlibabaActionTrail',
        #                           os.path.join('AlibabaActionTrail', 'ModelingRules', 'Alibaba_schema.jsom'))

    def run_validations(self):
        """
        Runs the bucket verifications.
        """
        self.run_basic_validations()

        if self.bucket_name == XSIAM_BUCKET:
            self.run_xsiam_bucket_validations()

    def is_bucket_valid(self):
        """
        Returns whether the bucket is valid.
        """
        logging.info(f"Bucket with name {self.bucket_name} is {'valid' if self.is_valid else 'invalid'}.")
        return self.is_valid


# def get_items_dict(pack_path, pack_id):
#     pack = Pack(pack_id, pack_path)
#     pack.collect_content_items()
#     return pack._content_items


def validate_bucket(service_account, storage_base_path, bucket_name, versions_dict, items_dict):
    """
    Creates the GCP and BucketVerifier objects and runs the bucket validations.
    """
    gcp = GCP(service_account, bucket_name, storage_base_path)
    bucket_verifier = BucketVerifier(gcp, bucket_name, versions_dict, items_dict)
    bucket_verifier.run_validations()
    return bucket_verifier.is_bucket_valid()


def get_args():
    parser = argparse.ArgumentParser(description="Check if the created bucket is valid")
    parser.add_argument('-s', '--service-account', help="Path to gcloud service account", required=False)
    parser.add_argument('-sb', '--storage-base_path', help="Path to storage under the marketplace-dist-dev bucket",
                        required=False)
    parser.add_argument('-b', '--bucket-name', help="Storage bucket name", default='All')
    parser.add_argument('-a', '--artifacts-path', help="path to artifacts from the script creating the test branch, "
                                                       "should contain json with dict of pack names and items to verify"
                                                       "and json with dict of pack names and versions to verify",
                        required=False)
    return parser.parse_args()


def read_json(path):
    with open(path, 'r') as file:
        return json.load(file)


def main():
    install_logging('verify_bucket.log', logger=logging)

    args = get_args()
    storage_base_path = args.storage_base_path
    service_account = args.service_account
    storage_bucket_name = args.bucket_name
    versions_dict = read_json(os.path.join(args.artifacts_path, 'versions_dict.json'))
    items_dict = read_json(os.path.join(args.artifacts_path, 'packs_items.json'))

    is_valid = True
    if storage_bucket_name != 'All':
        if storage_bucket_name not in [XSOAR_BUCKET, XSIAM_BUCKET]:
            logging.error('Storage bucket is not valid.')
            sys.exit(1)

        is_valid = validate_bucket(service_account, storage_base_path, storage_bucket_name, versions_dict, items_dict)
    else:
        is_xsoar_bucket_valid = validate_bucket(service_account, storage_base_path, XSOAR_BUCKET, versions_dict, items_dict)
        is_valid = validate_bucket(service_account, storage_base_path, XSIAM_BUCKET, versions_dict, items_dict) \
            and is_xsoar_bucket_valid

    if not is_valid:
        sys.exit(1)


if __name__ == "__main__":
    main()        
    logging.success('XSOAR and XSIAM buckets are valid!')
