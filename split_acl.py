#!/usr/bin/env python
from __future__ import unicode_literals

import os
import sys
import re
#import getpass
#import time
import ipaddress
from pprint import pprint
from ciscoconfparse import CiscoConfParse
from ciscoconfparse.ccp_util import IPv4Obj
#from collections import namedtuple
#import cidr_convert



PRINT_REMARKS = False			# True for print to screen, False no print to screen
SKIP_REMARKS = True 			# Skip the remark lines in export output
SPLIT_OBJECT_GROUPS = True		# 1 to loop trough object-group and printout rows
EXTRACT_OBJECT_GROUPS = True	# True is extract all object-group to single output (nested groeps not visible), output to JSON will alway be nested
FLATTEN_NESTED_LISTS = True		# True if the output of nested lists must be extracted to one list
SKIP_INACTIVE = True			# True to skip lines that are inactie (last word of ACL line)
SKIP_TIME_EXCEEDED = True		# Skip rules with time-ranges that have passed by

#OUTPUT_JSON_FILE = "split_acl.json"

input_config_file = "ciscoconfig.conf" 

# named tuples
#interface = namedtuple('interface', 'namedif')


def parseconfig(filename):
	return CiscoConfParse(filename)

def is_ipv4(ip):
	match = re.match("^(\d{0,3})\.(\d{0,3})\.(\d{0,3})\.(\d{0,3})$", ip)
	if not match:
		return False
	quad = []
	for number in match.groups():
		quad.append(int(number))
	if quad[0] < 1:
		return False
	for number in quad:
		if number > 255 or number < 0:
			return False
	return True

def flatten( alist ):
	# Flatten nested list to one list
     newlist = []
     for item in alist:
         if isinstance(item, list):
             newlist = newlist + flatten(item)
         else:
             newlist.append(item)
     return newlist



def get_acl_lines(parse, acl_name):
	"""
	Get ACL line by line and parse to split_acl_lines to analyse per word

	"""
	for acl_line in parse.find_objects(r'access-list\s'):
		if acl_name in acl_line.text:
			print("")
			acl_line_number = acl_line.linenum
			acl_line = acl_line.text.split(' ', 2)[2]
			# FILTER OUT LINES
			# First check if remark or ACL type
			#print("ACL 6 (remark): " + acl_line.partition(' ')[0]) 	
			if (acl_line.partition(' ')[0] == 'remark' and PRINT_REMARKS == True ) or acl_line.partition(' ')[0] == 'extended':
				print(acl_line_number), ":",
				print(acl_line)
				if (acl_line.partition(' ')[0] == 'remark' and SKIP_REMARKS == False ) or acl_line.partition(' ')[0] == 'extended':
					# Go further and split ACL
					split_acl_lines(parse, acl_line)
			

def get_og_content(parse, og_name, og_type):
	#parse = parseconfig(input_config_file)
	#og_types: protocol, network, service
	# network-object 
	all_og_items = list()
	if og_type == 'network':
		#print("NETWORK OBJECTS :" + og_name)
		og_items = iter(parse.find_all_children('object-group network '+ og_name, exactmatch=True))
		#itercars = iter(cars)
		next(og_items)
		
		for og_item in og_items:
			
			og_item_words = og_item.split()
			if og_item_words[0] != 'description' and og_item_words[0] != 'group-object' :
				#print(" " + og_item)
				# Check wether new object, group is used or valid IPv4 address
				if is_ipv4(og_item_words[1]):
					#print("Is IPv4 : " + og_item_words[1])
					# 2nd and 3rd word are subnet and netmask
					og_IP_item = og_item_words[1] + " " + og_item_words[2]
					#print(og_IP_item)
					all_og_items.append(og_IP_item)
				elif og_item_words[1] == 'host':
					all_og_items.append(og_item_words[2] + "  255.255.255.255")
				elif og_item_words[1] == 'object':
					## get object items
					#og_item_object = get_object_content(parse, og_item_words[2], og_type)
					all_og_items.append(get_object_content(parse, og_item_words[2], og_type))
				elif og_item_words[1] == 'network':
					print("TODO NETWORK TYPE")
				else:
					print("ERROR: object-group type " + og_item_words[1] + " not found")
			elif og_item_words[0] == 'group-object':
				#print(" " + og_item), 
				#now check first word is 'group-object'
				#print("GROUP-OBJECT")
				all_og_items.append(get_og_content(parse, og_item_words[1], 'network'))
	if FLATTEN_NESTED_LISTS == True:
		all_og_items = flatten(all_og_items)
	return all_og_items

def get_object_content(parse, object_name, o_type):
	#Instead of object-group there are also objects 
	#og_types: protocol, network, service
	# network-object 
	indent_space = "     "
	#print(indent_space + "finding objects for " + object_name)
	#print("")
	all_object_items = list()
	if o_type == 'network':
		o_items = iter(parse.find_all_children('^object network '+ object_name + '', exactmatch=True))
		#skip first item
		next(o_items)
		for o_item in o_items:
			o_item_words = o_item.split()
			#print(indent_space + o_item)
			if o_item_words[0] == 'subnet':
				#print(o_item_words[1])
				all_object_items.append(o_item_words[1] + " " + o_item_words[2])
			elif o_item_words[0] == 'host':
				all_object_items.append(o_item_words[1] + "  255.255.255.255")
			elif o_item_words[0] == 'description':
				o_item_desc = o_item[len("description "):]
			else:
				print("ERROR OBJECT " + o_item_words[0] +  " TYPE NOT FOUND")
	else:
		print("ERROR OBJECT TYPE " + o_type + " NOT SUPPORTED")

	return all_object_items


def get_acl_line_word(acl_line, word_nr):
	acl_words = acl_line.split()
	return acl_words[word_nr-1]

def split_acl_lines(parse, acl_line):	
	acl_length = len(acl_line.split())
	indent_space = "     "
	acl_words = acl_line.split()
	# FILTER LINES, DONT PROCESS FURTHER
	skip_this_line = False
	if SKIP_INACTIVE == True and (get_acl_line_word(acl_line, acl_length) == 'inactive'):
		skip_this_line = True
		print("SKIPPED! Inactive")
	# Check if a time filter is used and is exceeded
	if SKIP_TIME_EXCEEDED == True and (get_acl_line_word(acl_line, acl_length-1) == 'time-range'):
		skip_this_line = True
		# RUN FUNCTION TO CHECK TIME AND RETURN SKIP TRUE OR FALSE
		print("SKIPPED! time-range exceeded")
	# END FILTER
	# Set default section names in ACL row (space seperated) they can change based on object-groups
	acl_type_section = 1
	acl_action_section = 2
	acl_protocol_section =3
	acl_src_ip_section = 4
	acl_src_sn_section = 5
	acl_dst_ip_section = 6
	acl_dst_sn_section = 7
	acl_port_section = 8
	#check if line is extended or remark line, if remark this will the remark till overwritten

	# define empty variables
	acl_type = ''
	acl_action = ''
	acl_protocols_in_og = False
	acl_protocol_og = ''
	acl_protocol = ''
	acl_source_in_og = False
	acl_source_sn = ''
	acl_source_nm = ''
	acl_source_og = ''
	acl_dst__in_og = False
	acl_dst_sn = ''
	acl_dst_nm = ''
	acl_dst_og = ''


	# define empty variables
	acl_type = get_acl_line_word(acl_line, acl_type_section)
	if acl_type != 'remark' and not skip_this_line:
		acl_action = get_acl_line_word(acl_line, acl_action_section)
		
		acl_protocol = get_acl_line_word(acl_line, acl_protocol_section)
		#check if protocl is object-group
		if acl_protocol == 'object-group':
			acl_protocols_in_og = True
			acl_protocol_og = get_acl_line_word(acl_line, acl_protocol_section+1)
			# extend source and destination words
			acl_src_ip_section = acl_src_ip_section + 1
			acl_src_sn_section = acl_src_sn_section + 1
			acl_dst_ip_section = acl_dst_ip_section + 1
			acl_dst_sn_section = acl_dst_sn_section + 1
			acl_port_section = acl_port_section + 1
		else:
			acl_protocols_in_og = False

		# Get source
		acl_source_sn = get_acl_line_word(acl_line, acl_src_ip_section)
		if acl_source_sn == 'object-group':
			acl_source_in_og = True
			acl_source_og = get_acl_line_word(acl_line, acl_src_ip_section+1)
			acl_source_og_items = get_og_content(parse, acl_source_og, 'network')				# CHECK IF NETWORK VARIABLE SET
		elif acl_source_sn == 'host':
			## Next item is host IP and not subnetmask. We generate default subnetmask
			acl_source_sn = get_acl_line_word(acl_line, acl_src_sn_section)
			acl_source_nm = '255.255.255.255'
		elif 'any' in acl_source_sn:	# check wordt as it can be any or any4 or any6
			## Next item is host IP and not subnetmask. We generate default subnetmask
			acl_source_sn = '0.0.0.0'
			acl_source_nm = '0.0.0.0'
			# rest of the word indexes -1
			acl_dst_ip_section = acl_dst_ip_section - 1
			acl_dst_sn_section = acl_dst_sn_section - 1
			acl_port_section = acl_port_section - 1
		else:
			acl_source_in_og = False
			acl_source_nm = get_acl_line_word(acl_line, acl_src_sn_section)
		
		# Get destination
		acl_dst_sn = get_acl_line_word(acl_line, acl_dst_ip_section)
		if acl_dst_sn == 'object-group':
			acl_dst_in_og = True
			acl_dst_og = get_acl_line_word(acl_line, acl_dst_ip_section+1)
			acl_dst_og_items = get_og_content(parse, acl_dst_og, 'network')						# CHECK IF NETWORK VARIABLE SET
		elif acl_dst_sn == 'host':
			## Next item is host IP and not subnetmask. We generate default subnetmask
			acl_dst_sn = get_acl_line_word(acl_line, acl_dst_sn_section)
			acl_dst_nm = '255.255.255.255'
		elif 'any' in acl_dst_sn:	# check wordt as it can be any or any4 or any6
			## Next item is host IP and not subnetmask. We generate default subnetmask
			acl_dst_sn = '0.0.0.0'
			acl_dst_nm = '0.0.0.0'
			# rest of the word indexes -1
			acl_port_section = acl_port_section - 1			
		else:
			acl_dst_in_og = False
			acl_dst_nm = get_acl_line_word(acl_line, acl_dst_sn_section)

		# Get port settings
		#how many words
		acl_port_words = acl_length - acl_port_section
		# can be negative, only process further when positive
		if acl_port_words > 0:
			acl_total_port_words = acl_port_words + acl_port_section
			acl_port_first = get_acl_line_word(acl_line, acl_port_section)
			# debug print all words:
			#for i in range(acl_port_section, acl_total_port_words+1):
			#	print("PORTS_ACL_WORD "), i,
			#	print(" : " + get_acl_line_word(acl_line, i))
			if acl_port_first == 'eq':
			# if first wordt is 'eq' one port will follow
				print("port match is 1 port")
				#acl_port_used =

			# if first wordt is 'range' couple of words/ports will follow, space seperated
			if acl_port_first == 'range':
			# if first wordt is 'eq' one port will follow
				print("port match is range of ports")
				#acl_port_used =


			# if first wordt is 'object-range' a group (of groups) will follow

			# if word is time-range followed by time setting. This is a temporary rule


	# PRINT 
	if acl_type != 'remark' and not skip_this_line:
		print("acl_type : " + acl_type)
		print("acl_action : " + acl_action)
		if (acl_protocols_in_og):
			print("acl_protocol_og: " + acl_protocol_og)
			if SPLIT_OBJECT_GROUPS == True:
				print(indent_space + "og_objects:")
		else:
			print("acl_protocol : " + acl_protocol)
		
		print("******* SOURCE: *******")
		if acl_source_og != '':
			print("acl_source_og : " + acl_source_og)
			if SPLIT_OBJECT_GROUPS == True:
				#convert list to string for print
				str_acl_source_og_items = '\n        '.join(map(str, acl_source_og_items))
				print(indent_space + "og_objects:" + str_acl_source_og_items)

		else:
			print("acl_source_sn : " + acl_source_sn)
			print("acl_source_nm : " + acl_source_nm) 
		print("****** DESTINATION: ******")
		if acl_dst_og != '':
			print("acl_dst_og : " + acl_dst_og)
			if SPLIT_OBJECT_GROUPS == True:
				#convert list to string for print
				str_acl_dst_og_items = '\n        '.join(map(str, acl_dst_og_items))
				print(indent_space + "og_objects:" + str_acl_dst_og_items)
		else:
			print("acl_dst_sn : " + acl_dst_sn)
			print("acl_dst_nm : " + acl_dst_nm) 
		if acl_port_words > 0:
			print("******** PORTS: ********")
			print("ACL WOORDEN"), acl_length
			print("WOORDEN VOOR PORTS "), acl_port_words
		else:
			print("NO PORTS IN ACL - SEE SERVICE GROUP")




def main():
	print("Read config file")

	parse = parseconfig(input_config_file)
	pprint(parse)
	print("")

	print("      get ACL info")
	get_acl_lines(parse, "Interconnect_access_in")


#	acl_source_og = "BNS_Beheer_Segment"
#	acl_source_og_items = get_og_content(parse, acl_source_og, 'network')
#	if FLATTEN_NESTED_LISTS == True:
#		acl_source_og_items = flatten(acl_source_og_items)

	#print("")
	#pprint(acl_source_og_items)

if __name__ == "__main__":
	main()
