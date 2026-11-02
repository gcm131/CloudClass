#!/bin/bash

# Define the roles to be deleted
ROLES=("itmo-uploader-role" "itmo-viewer-role")

for ROLE_NAME in "${ROLES[@]}"; do
    echo "========================================="
    echo "Processing deletion for: $ROLE_NAME"
    echo "========================================="

    # 1. Check if the role actually exists
    if ! aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
        echo "Role '$ROLE_NAME' does not exist or is already deleted. Skipping."
        continue
    fi

    # 2. Detach and remove Instance Profiles (Crucial for EC2 roles)
    echo "Checking for attached EC2 Instance Profiles..."
    INSTANCE_PROFILES=$(aws iam list-instance-profiles-for-role --role-name "$ROLE_NAME" --query "InstanceProfiles[*].InstanceProfileName" --output text)
    
    for PROFILE in $INSTANCE_PROFILES; do
        if [ -n "$PROFILE" ] && [ "$PROFILE" != "None" ]; then
            echo "Removing role from instance profile: $PROFILE"
            aws iam remove-role-from-instance-profile --instance-profile-name "$PROFILE" --role-name "$ROLE_NAME"
            
            # Optional: Delete the instance profile container if it matches the role name
            if [ "$PROFILE" == "$ROLE_NAME" ]; then
                echo "Deleting instance profile container: $PROFILE"
                aws iam delete-instance-profile --instance-profile-name "$PROFILE"
            fi
        fi
    done

    # 3. Detach Managed Policies
    echo "Detaching managed policies..."
    MANAGED_POLICIES=$(aws iam list-attached-role-policies --role-name "$ROLE_NAME" --query "AttachedPolicies[*].PolicyArn" --output text)
    for POLICY_ARN in $MANAGED_POLICIES; do
        if [ -n "$POLICY_ARN" ] && [ "$POLICY_ARN" != "None" ]; then
            echo "Detaching policy ARN: $POLICY_ARN"
            aws iam detach-role-policy --role-name "$ROLE_NAME" --policy-arn "$POLICY_ARN"
        fi
    done

    # 4. Delete Inline Policies
    echo "Deleting inline policies..."
    INLINE_POLICIES=$(aws iam list-role-policies --role-name "$ROLE_NAME" --query "PolicyNames" --output text)
    for POLICY_NAME in $INLINE_POLICIES; do
        if [ -n "$POLICY_NAME" ] && [ "$POLICY_NAME" != "None" ]; then
            echo "Deleting inline policy: $POLICY_NAME"
            aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME"
        fi
    done

    # 5. Delete the Role itself
    echo "Deleting IAM Role: $ROLE_NAME"
    if aws iam delete-role --role-name "$ROLE_NAME"; then
        echo "Successfully deleted role: $ROLE_NAME"
    else
        echo "ERROR: Failed to delete role $ROLE_NAME"
    fi
    echo ""
done

echo "Cleanup process completed."
